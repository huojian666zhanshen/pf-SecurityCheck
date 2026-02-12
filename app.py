# security_check_service/app.py
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="SecurityCheckTool", version="0.1.0")

# MATPOWER 索引（当 bus/branch 是 list[list] 时用）
BUS_I = 0
BUS_VM = 7
BR_RATEA = 5  # MVA
# 对于你纯潮流工具的 branch dict：Pf/Qf/rateA_MVA 已经解析好了，不用索引

class Limits(BaseModel):
    vmin: float = Field(0.95, description="Voltage lower bound (p.u.)")
    vmax: float = Field(1.05, description="Voltage upper bound (p.u.)")
    # 热稳阈值：如果 branch 给了 rateA，就按它；否则不判
    thermal_eps: float = Field(1e-6, description="Small epsilon for thermal check")

class SecurityRequest(BaseModel):
    pf: Dict[str, Any] = Field(..., description="Power flow result JSON (from your PF tool)")
    limits: Limits = Field(default_factory=Limits)

def _extract_bus_vm(pf: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    统一抽取 bus 列表为 dict 形式：[{id, Vm_pu}, ...]
    支持：
    - pf['bus'] = list[dict] with Vm_pu/Vm
    - pf['bus'] = list[list] MATPOWER row (Vm at col 7)
    """
    bus = pf.get("bus")
    if not isinstance(bus, list) or not bus:
        return []

    # case1: list[dict]
    if isinstance(bus[0], dict):
        out = []
        for r in bus:
            if not isinstance(r, dict):
                continue
            bid = r.get("id", r.get("bus_i", None))
            # 兼容字段名
            vm = r.get("Vm_pu", r.get("Vm", r.get("vm", r.get("VM", None))))
            if bid is None or vm is None:
                continue
            out.append({"id": int(bid), "Vm_pu": float(vm)})
        return out

    # case2: list[list] MATPOWER
    if isinstance(bus[0], list):
        out = []
        for row in bus:
            if not isinstance(row, list) or len(row) <= BUS_VM:
                continue
            bid = int(row[BUS_I])
            vm = float(row[BUS_VM])
            out.append({"id": bid, "Vm_pu": vm})
        return out

    return []

def _extract_branch_flows(pf: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    统一抽取支路潮流，用于热稳：
    支持你 PF 输出的 branch dict:
      {idx,fbus,tbus,Pf_MW,Qf_Mvar,rateA_MVA}
    若不存在 Pf/Qf/rateA，则跳过热稳判别。
    """
    br = pf.get("branch")
    if not isinstance(br, list) or not br:
        return []
    if not isinstance(br[0], dict):
        return []  # 你纯潮流服务现在是 dict 输出；若未来变 list[list] 可再扩展
    out = []
    for r in br:
        if not isinstance(r, dict):
            continue
        idx = r.get("idx")
        Pf = r.get("Pf_MW", None)
        Qf = r.get("Qf_Mvar", None)
        rateA = r.get("rateA_MVA", None)
        out.append({
            "idx": int(idx) if idx is not None else None,
            "Pf_MW": None if Pf is None else float(Pf),
            "Qf_Mvar": None if Qf is None else float(Qf),
            "rateA_MVA": None if rateA is None else float(rateA),
        })
    return out

def _score_from_violations(v_viol: int, thermal_viol: int, v_margin_pen: float, thermal_over_pen: float) -> float:
    """
    简单可解释的打分：越大越好（0~1 附近）
    你后面可以换更复杂的权重/分段函数。
    """
    # 先构造一个非负损失
    loss = 0.0
    loss += 1.0 * v_viol
    loss += 0.8 * thermal_viol
    loss += 5.0 * v_margin_pen
    loss += 2.0 * thermal_over_pen
    # 映射到 (0,1]
    return 1.0 / (1.0 + loss)

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/security_check")
def security_check(req: SecurityRequest):
    pf = req.pf
    lim = req.limits

    if not isinstance(pf, dict):
        raise HTTPException(status_code=400, detail="pf must be an object")

    # 1) 电压越限
    buses = _extract_bus_vm(pf)
    if not buses:
        raise HTTPException(status_code=400, detail="pf.bus missing or unrecognized")

    v_viol = []
    vmin = +1e9
    vmax = -1e9
    v_margin_pen = 0.0

    for b in buses:
        vm = float(b["Vm_pu"])
        vmin = min(vmin, vm)
        vmax = max(vmax, vm)
        if vm < lim.vmin:
            sev = lim.vmin - vm
            v_margin_pen += sev
            v_viol.append({"type": "voltage_low", "bus": b["id"], "value_pu": vm, "limit_pu": lim.vmin, "severity": sev})
        elif vm > lim.vmax:
            sev = vm - lim.vmax
            v_margin_pen += sev
            v_viol.append({"type": "voltage_high", "bus": b["id"], "value_pu": vm, "limit_pu": lim.vmax, "severity": sev})

    # 2) 热稳越限（如果有 Pf/Qf/rateA）
    branches = _extract_branch_flows(pf)
    t_viol = []
    thermal_over_pen = 0.0

    for r in branches:
        rateA = r.get("rateA_MVA")
        Pf = r.get("Pf_MW")
        Qf = r.get("Qf_Mvar")
        if rateA is None or Pf is None or Qf is None or rateA <= 0:
            continue
        S = math.sqrt(Pf*Pf + Qf*Qf)
        if S > rateA + lim.thermal_eps:
            over = (S / rateA) - 1.0
            thermal_over_pen += over
            t_viol.append({"type": "thermal", "branch_idx": r.get("idx"), "value_MVA": S, "limit_MVA": rateA, "severity": over})

    violations = v_viol + t_viol
    score = _score_from_violations(
        v_viol=len(v_viol),
        thermal_viol=len(t_viol),
        v_margin_pen=v_margin_pen,
        thermal_over_pen=thermal_over_pen
    )

    return {
        "ok": True,
        "score": score,
        "summary": {
            "n_viol": len(violations),
            "n_voltage_viol": len(v_viol),
            "n_thermal_viol": len(t_viol),
            "vmin": vmin,
            "vmax": vmax,
            "v_margin_pen": v_margin_pen,
            "thermal_over_pen": thermal_over_pen
        },
        "violations": violations
    }

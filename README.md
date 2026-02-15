# SecurityCheckTool

`SecurityCheckTool` 是一个用于电力系统安全检查的工具，基于 FastAPI 提供电压和热稳定性（热稳）检查功能。通过这个工具，您可以验证电力系统的潮流计算结果是否符合电压和热稳要求，确保系统的安全性。

## 主要功能

1. **电压检查：**
    - 检查每个母线的电压是否在设定的电压上下限 (`vmin` 和 `vmax`) 范围内。
    - 如果电压超出上下限，系统会返回违规信息，指明违规母线的ID、电压值和超限的严重程度。
2. **热稳定性检查：**
    - 检查每个支路的功率流是否超出热稳阈值（`rateA_MVA`）。
    - 如果支路功率流超出限值，系统会返回热稳违规信息，指明违规支路、功率流值和超限的严重程度。
3. **评分机制：**
    - 根据电压违规、热稳违规的数量以及电压/热稳违规的严重程度，系统会生成一个安全评分，值范围从 0 到 1，越大表示越安全。

## 安装

```bash
# 克隆该仓库
git clone <https://github.com/huojian666zhanshen/pf-SecurityCheck.git>

# 创建并激活虚拟环境
python -m venv venv
source venv/bin/activate  # 对于Windows系统，使用 venv\\Scripts\\activate

# 安装依赖
pip install -r requirements.txt
运行应用
在本地运行 FastAPI 应用：

uvicorn security_check_service:app --reload
访问应用界面：<http://127.0.0.1:8000>

API 接口
健康检查 (/health)
检查服务是否运行正常。
```

## API 接口

健康检查 (/health)
检查服务是否运行正常。

## GET /health

```json
响应:

{
  "ok": true
}
安全检查 (/security_check)
进行电力系统的安全检查，验证电压和热稳是否符合要求。

```

## POST /security_check

```json
请求体：

{
  "pf": {
    "bus": [
      {"id": 1, "Vm_pu": 0.96},
      {"id": 2, "Vm_pu": 1.03}
    ],
    "branch": [
      {"idx": 0, "Pf_MW": 50, "Qf_Mvar": 20, "rateA_MVA": 100},
      {"idx": 1, "Pf_MW": 120, "Qf_Mvar": 50, "rateA_MVA": 100}
    ]
  },
  "limits": {
    "vmin": 0.95,
    "vmax": 1.05,
    "thermal_eps": 1e-6
  }
}
请求参数说明：

pf: 电力潮流计算结果，包括每个母线和支路的电压和功率流数据。

limits: 安全阈值配置，定义电压上下限和热稳阈值。

响应：

{
  "ok": true,
  "score": 0.95,
  "summary": {
    "n_viol": 2,
    "n_voltage_viol": 1,
    "n_thermal_viol": 1,
    "vmin": 0.95,
    "vmax": 1.05,
    "v_margin_pen": 0.01,
    "thermal_over_pen": 0.2
  },
  "violations": [
    {
      "type": "voltage_low",
      "bus": 1,
      "value_pu": 0.96,
      "limit_pu": 0.95,
      "severity": 0.01
    },
    {
      "type": "thermal",
      "branch_idx": 1,
      "value_MVA": 120,
      "limit_MVA": 100,
      "severity": 0.2
    }
  ]
}
响应参数说明：

ok: 状态标识，表示请求是否成功。

score: 安全评分，越接近 1 越表示系统越安全。

summary: 安全检查的摘要，包括电压违规和热稳违规的数量、违规的电压范围、热稳的处罚值等。

violations: 详细的违规信息，列出了电压和热稳的具体违规情况
```

## 依赖

### FastAPI: Web框架

### Pydantic: 数据验证

### math: 数学计算（用于热稳检查

## 贡献

欢迎提交PR，报告问题，或者提供反馈。我们鼓励开源贡献，任何有助于改进本工具的想法都非常欢迎。

## 许可证

该项目使用 MIT 许可证。

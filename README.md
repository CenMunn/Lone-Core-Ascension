# 独核通天 · Lone Core: Ascension

基于 Gradio、DeepSeek 与通义万相的交互式冒险故事生成系统。玩家扮演陆凌霄，在核心纪元的废墟、地下城与通天塔中探索，通过选择和自由行动推进叙事。

![废土与通天塔](output/brand/tower-background-gpt.png)

## 功能

- 流式故事文本、情景推荐与自由行动；普通续写独立开放，关键剧情按条件解锁。
- 根据当前场景、人物卡和状态生成插图，后台处理图片与配音。
- 独行成长、核心净化与吸收、能力残响融合、装备打造和图鉴。
- 核心人物好感度、详细人物档案与参考图。
- 节点分支回溯、命名存档槽、ZIP 导入导出。
- 多人投票共同决策，以及中文与英文的主要交互。
- 正常冒险、标注清楚的章节演示，以及不调用模型的离线规则模式。

## 安装与运行

需要 Python 3.11 或更高版本。实际开发环境为 Windows、Python 3.14.4、Gradio 6.30.0。

```powershell
git clone https://github.com/CenMunn/Lone-Core-Ascension.git
cd Lone-Core-Ascension
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`，配置自己的文本服务和百炼密钥。不要把真实密钥提交到 Git。变量示例：

```dotenv
DEEPSEEK_API_KEY=your_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
DASHSCOPE_API_KEY=your_key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/api/v1
DASHSCOPE_MODEL=wan2.5-t2i-preview
DASHSCOPE_IMAGE_SIZE=1280*1280
```

模型和服务地址须与账号权限匹配。实验中使用过 `deepseek-flash`；公开配置请选择自己账号支持的 OpenAI 兼容模型。图片模块支持万相 2.1 与 2.5，不可直接混用 2.6 的协议。

```powershell
.\.venv\Scripts\python.exe -m duhe.app_v2_draft
```

浏览器访问 **http://127.0.0.1:7865/**，也可双击 `启动独核通天_新版.bat`。macOS/Linux 使用 `.venv/bin/python`，复制配置用 `cp .env.example .env`。

初次启动会创建本地 `data/`。语音使用 Edge TTS，需要网络；多角色音频合成还需安装 ffmpeg 并加入 PATH。离线规则模式不生成真实故事插图。

## 游玩提示

创建冒险后进入初遇剧情。插图在正文上方，系统、背包和图鉴在旁边。净化、吸收和换装不推进剧情回合；一场战斗只在开战时计入一个剧情回合，战斗内出招另计。自由行动描述主角想做的事情，结果由模型结合情节生成，不保证目标必然成功。

自动配图、自动配音可分别开关。图片任务失败时，优先使用“生成或恢复配图”恢复已有任务。重要进度请导出 ZIP；个人存档和数据库不会随仓库分发。

## 项目结构

```text
duhe/app_v2_draft.py  Gradio 界面与事件
duhe/engine_v2.py     工作流与后台任务
duhe/providers.py    文本模型与配置
duhe/image_jobs.py   万相任务提交、查询和下载
duhe/prompts.py      故事与视觉提示
duhe/storage.py      SQLite 分支与存档
config/              魔物、装备、能力等配置
tests/               自动化测试
output/brand/        网页背景与游戏徽标
```

## 测试与限制

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

2026-11-13 的本地回归为 **351 项测试与 6 项子测试通过**。其中包含受控接口和离线规则测试，不代表全部真实模型请求均成功。完整路线曾以离线机械化策略在85个剧情回合触发终局，不能视为真人完整通关记录。

人物脸部、伤痕、装备和对白说话人仍可能出现偏差；档案参考图尚未作为默认场景图的身份条件。部分提示与人物档案仍为中文或双语，尚非完整本地化。图像反馈由用户观察确认，当前没有自动识图闭环。

曾出现万相任务已成功而本机下载失败的问题，网络、DNS 与代理均可能影响结果。程序保留任务 ID 并提供备用下载路径，但不保证所有网络环境均可恢复。停止等待不等于取消远端计算。默认仅监听本机，多人房间口令不替代公网认证。

## 课程说明

本项目用于《高级AI应用全栈开发》实验四，实践 LLM 流式调用、文生图工作流、提示工程、Gradio Blocks、异步处理与分支记忆。网页背景为预先生成的美术资源；游玩场景插图由配置的万相服务生成。外部模型与语音服务适用各自的使用条件。

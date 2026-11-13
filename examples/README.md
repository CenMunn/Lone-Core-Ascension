# 同提示词四种接口教学

只从进程环境变量读取密钥；导入 Python 示例没有网络调用。以下命令在项目根目录手动运行，会产生真实API费用，不在自动测试执行。

`lesson_prompt.json` 是共用提示词源：同一功能的 HTTP、SDK、curl 与 Postman 使用相同正文；图片参数固定 n=1、seed=42、prompt_extend=false。种子不保证跨后端/模型输出完全一致。

1. HTTP：`python -m examples.http_demo text` 或 `python -m examples.http_demo image`。
2. SDK：`python -m examples.sdk_demo text` 或 `python -m examples.sdk_demo image`。文本用OpenAI 2.x，图片用DashScope 2.x的 `Client.images.jobs.create/fetch`，与legacy `ImageSynthesis` 区分。
3. curl（PowerShell）：`./examples/curl_demo.ps1 -Kind text`、`-Kind image`；随后 `-Kind poll -TaskId 保存的ID`。不设置curl重试，提交断线时去控制台核实，不能直接重发。
4. Postman：导入 `postman_collection.json`；在本地环境填写 `text_key/image_key`（设为secret，勿同步或导出），填写地域匹配的base和启用的model。手动依次运行文本请求或图片提交/查询。集成集合生成脚本 `python -m examples.make_postman` 从相同提示词文件重建集合，无网络。

图片恢复：HTTP/SDK 命令加 `--task-id 已有任务ID`，只查询，不再次提交。SDK成功后用HTTP命令恢复同一个taskid，将校验后的图片下载到 `outputs/http-scene.png`。任务与链接通常24小时有效；下载URL是签名凭据，不复制到报告/日志。

百炼文本兼容端点为 `https://dashscope.aliyuncs.com/compatible-mode/v1`，设置 `DEEPSEEK_API_KEY/DEEPSEEK_BASE_URL/DEEPSEEK_MODEL`；百炼图片原生端点为 `https://dashscope.aliyuncs.com/api/v1`，设置 `DASHSCOPE_API_KEY/DASHSCOPE_BASE_URL/DASHSCOPE_MODEL`。Key、模型和端点地域必须一致。生产应用还兼容BL_DEEPSEEK别名，教学脚本使用统一DEEPSEEK命名。

万相2.1默认1024*1024，2.5默认1280*1280；本例禁止将2.6模型放入2.1/2.5协议。HTTP async头与input/parameters位置不可省略或互换。

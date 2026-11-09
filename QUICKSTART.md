# 图形界面运行指南

1. 在 PyCharm 中单独打开本文件所在文件夹。
2. 选择 Python 3.12 解释器，你已有的 digit-ai 环境可用于本地演示。
3. 在 Python 软件包面板检查 Flask、numpy、scikit-learn，缺少时按 requirements.txt 安装。
4. 右键 app.py 并运行，打开运行窗口给出的本地地址。
5. 保持本地演示模式，点击运行实验，观察算法输出和中间过程。

## 连接自己的模型

在项目中复制 .env.example，副本命名为 .env。用已有服务商的 API 密钥、地址和模型名称替换示例。DeepSeek 地址使用 https://api.deepseek.com，OpenRouter 使用 https://openrouter.ai/api/v1。重启 app.py 后，在网页中选择连接云端模型。密钥由服务端读取，.env 已被 Git 忽略。单次运行限制最多六次 API 尝试，实际调用可能计费。浏览器显示本次调用与耗时，未运行的云端能力需自行验证。

## 本地验证

在 PyCharm 中运行 tests 中的单元测试，或在项目终端运行 python -m unittest discover -s tests。这些检查覆盖代码中的关键边界，README 中说明了进一步评估方法。

## 上传 GitHub

将本文件夹作为独立项目提交。包含 README、代码、requirements.txt、.env.example 和样例数据。在提交窗口检查 .env、.idea 和运行缓存未被勾选。介绍项目时注明实际实现、演示数据来源与已完成的验证范围。

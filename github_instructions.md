# 将VTT字幕翻译系统提交到GitHub的步骤

以下是将此项目提交到GitHub的详细步骤：

## 1. 创建GitHub仓库

1. 登录到你的GitHub账户
2. 点击右上角的"+"图标，选择"New repository"
3. 填写仓库名称，例如"vtt-translator"
4. 添加描述："A tool for translating VTT subtitles from English to Chinese using AWS Bedrock Claude"
5. 选择"Public"或"Private"
6. 不要勾选"Initialize this repository with a README"
7. 点击"Create repository"

## 2. 将本地仓库推送到GitHub

在本地终端中执行以下命令：

```bash
# 添加远程仓库
git remote add origin https://github.com/YOUR_USERNAME/vtt-translator.git

# 推送到GitHub
git push -u origin main
```

将`YOUR_USERNAME`替换为你的GitHub用户名。

## 3. 验证提交

1. 刷新GitHub仓库页面
2. 确认所有文件都已成功上传
3. 检查README.md是否正确显示

## 4. 设置GitHub Pages（可选）

如果你想为项目创建一个简单的网站：

1. 在GitHub仓库页面，点击"Settings"
2. 滚动到"GitHub Pages"部分
3. 在"Source"下拉菜单中选择"main"分支
4. 点击"Save"

## 5. 添加协作者（可选）

如果你想邀请其他人参与项目：

1. 在GitHub仓库页面，点击"Settings"
2. 点击"Manage access"
3. 点击"Invite a collaborator"
4. 输入用户名或电子邮件地址
5. 点击"Add collaborator"

## 注意事项

- 确保不要将敏感信息（如API密钥）提交到公共仓库
- 定期更新.gitignore文件以排除不需要的文件
- 考虑添加LICENSE文件以明确项目的使用条款
# 方案 A · 日股双动量实盘助手（手机 PWA + GitHub Actions 自动更新）

> **隐私边界**：本仓库仅托管**公开行情信号计算**与静态网页，**不包含任何个人持仓、金额或账户信息**。你的持仓与取得单价只保存在你自己的手机/电脑浏览器本地，或通过个人私有 Gist 同步。

## 5 分钟一次性部署到你的 GitHub（永久免费）

### 第 1 步：在 GitHub 新建一个 Public 仓库
1. 用你的 Google 关联账号登录 [GitHub](https://github.com) → 右上角 `+` → **New repository**。
2. 仓库名填例如 `scheme-a-signal`，勾选 **Public**（免费账号需 Public 才能启用 GitHub Pages），不要勾选 Initialize README → 点 **Create repository**。

### 第 2 步：把本 `webapp` 文件夹推送上去
在 Windows 终端进入本目录（`webapp`）执行（把 `<你的用户名>` 换成你的 GitHub 用户名）：

```powershell
cd "c:\Users\X64\Desktop\SAI\4.0 Antigravity\0.0 Self\日股交易策略\webapp"
git init -b main
git add .
git commit -m "init: Scheme A PWA and daily signal workflow"
git remote add origin https://github.com/<你的用户名>/scheme-a-signal.git
git push -u origin main
```

### 第 3 步：打开 GitHub Pages（生成手机网址）
1. 进入刚建好的仓库 → **Settings** → 左侧 **Pages**。
2. **Source** 下拉框直接选 **`GitHub Actions`**（会自动保存）。
3. 进入仓库 **Actions** 标签 → 点击左侧 `Daily Scheme A Signal & Pages Deploy (07:30 JST)` → 点一次 **Run workflow** 触发首次实时部署。
4. 等待约 1 分钟绿勾完成后，即可通过 `https://<你的用户名>.github.io/scheme-a-signal/` 访问你的专属手机网址！

### 第 4 步：日常自动更新（永久零维护）
每个周一至周五 **07:30 JST**（及 08:15 JST 备份），GitHub 云端会自动拉取最新 Yahoo 收盘数据、跑防拆股清洗并重新部署网页，无需开电脑！

### 第 5 步：添加到手机桌面（像原生 App 一样用）
- **iPhone (Safari)**：打开上面的网址 → 底部 **分享按钮** → **添加到主屏幕**。
- **Android (Chrome)**：打开网址 → 右上角 `⋮` → **添加到主屏幕 / 安装应用**。

---

## 换电脑 / 手机↔Mac↔Windows 同步持仓
- **最简方式**：点击网页右上角 **☁️ 同步** → 复制状态码发给自己，在另一台设备粘贴导入即可。
- **全自动云同步**：在 GitHub Settings → Developer settings → Personal access tokens (Tokens classic) 生成一个**只勾选 `gist` 权限**的 Token，填入网页「☁️ 同步」中点一次「上传到私有 Gist」，把生成的 Gist ID 填到 Mac/Windows 即可三端私密同步。

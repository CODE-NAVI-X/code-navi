# Code Navi Frontend

学生端使用 Next.js 16、React 19 和 TypeScript。最低 Node.js 版本为 20.9。

从仓库根目录完成 Python 后端安装后，安装并启动前端：

```bash
cd frontend
npm ci
npm run dev -- --port 3000
```

默认访问 `http://127.0.0.1:8000`。后端地址不同时，复制 `.env.example` 为 `.env.local` 并修改 `NEXT_PUBLIC_CODE_NAVI_API_URL`，然后重新启动或构建前端。`.env.local` 不得提交。

质量检查：

```bash
npm run lint
npx tsc --noEmit
npm run build
```

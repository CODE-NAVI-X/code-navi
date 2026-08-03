# 知识点学习模块：架构决策与技术落地规范 (ADR)

> **文档性质**：架构决策记录 (Architectural Decision Record) 与 Vibecoding / Cline 执行规范  
> **适用范围**：`code-navi` 后端 API 设计、PoC 持久化层方案、`OpenMAIC` 前端数据流转  
> **设计核心原则**：**低耦合、低门槛跑通、渐进式演进、极易纠正与扩展**  
> **制定时间**：2026-07-21  

---

## 📑 目录

1. [全局设计原则与防坏死机制](#一-全局设计原则与防坏死机制)
2. [架构决策一：后端 API 入口与模块化路由结构](#二-架构决策一后端-api-入口与模块化路由结构)
3. [架构决策二：PoC 第一版持久化方案 (SQLite ➔ PostgreSQL 平滑演进)](#三-架构决策二poc-第一版持久化方案-sqlite--postgresql-平滑演进)
4. [架构决策三：课后流转跳转契约 (Go 按钮双轮驱动传递)](#四-架构决策三课后流转跳转契约-go-按钮双轮驱动传递)
5. [Cline / AI Vibecoding 落地执行 Checklists](#五-cline--ai-vibecoding-落地执行-checklists)

---

## 一、 全局设计原则与防坏死机制

为了保证项目在后续迭代中**“决策合适、改动成本极低、易于纠正与平滑升级”**，本规范遵循以下三项防坏死原则：

1. **强隔离不反向侵入**：`src/kernel` 保持 100% 平台无关，所有业务 API 与服务全部收拢在 `src/code_navi` 目录内。
2. **依赖倒置 (DIP)**：持久化层与业务逻辑解耦，通过 ORM / DAO 抽象屏蔽底层数据库差异，未来从 SQLite 切换至 PostgreSQL 时业务代码零改动。
3. **容错降级 (Fallback)**：跨页面 / 跨模块数据传递采用“内存状态 + URL 参数恢复”双保险，防止单点状态丢失。

---

## 二、 架构决策一：后端 API 入口与模块化路由结构

### 2.1 决策内容
采用 **“业务模块独立 Router + 宿主轻量 Server 网关”** 的双层解耦结构。

### 2.2 目录与文件规范
```text
src/code_navi/
├── learning/                 # 知识点学习业务模块 (高内聚)
│   ├── __init__.py
│   ├── router.py             # 独立 API 路由 (APIRouter)
│   ├── services.py           # 核心服务 (QueryOrchestrator, PromptDecontaminationEngine)
│   └── schemas.py            # Pydantic 请求与响应 Data Model
│
├── server.py                 # 主 FastAPI 引擎与网关入口 (轻量级装配)
```

### 2.3 代码实现规范
* **`src/code_navi/learning/router.py`**：
  ```python
  from fastapi import APIRouter
  
  router = APIRouter(prefix="/api/v1/learning", tags=["Learning"])
  
  @router.post("/explain")
  async def explain_knowledge_point(request: ExplainRequest):
      # 业务逻辑交由 services.py 处理
      return await learning_service.explain(request)
  ```
* **`src/code_navi/server.py`**：
  ```python
  from fastapi import FastAPI
  from fastapi.middleware.cors import CORSMiddleware
  from code_navi.learning.router import router as learning_router
  
  app = FastAPI(title="Code Navi Backend API", version="0.1.0")
  
  # CORS 配置
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  
  # 挂载各模块路由
  app.include_router(learning_router)
  ```

### 2.4 易于变动与纠正分析
- 若后续需要增加【代码练习 (`practice`)】或【科研助手 (`research`)】路由，只需在各自目录下编写 `router.py`，并在 `server.py` 中增加一行 `app.include_router(...)` 即可，**互不干涉，零重构成本**。

---

## 三、 架构决策二：PoC 第一版持久化方案 (SQLite ➔ PostgreSQL 平滑演进)

### 3.1 决策内容
第一版 PoC 推荐采用 **SQLite + SQLAlchemy ORM / SQLModel** 方案。数据库文件存储在本地轻量路径：`.code-navi/learning_poc.db`。

### 3.2 为什么这是当前最合适的决策？
1. **零配置、秒启动**：Python 内置 SQLite 支持，无需本地配置 PostgreSQL 实例、用户密码或环境变量，开箱即用。
2. **极易做自动化测试**：单测时可直接在内存模式 (`sqlite:///:memory:`) 下快速执行，极大地提升测试与开发体验。

### 3.3 数据库模型映射 (SQLAlchemy)
```python
# src/code_navi/learning/models.py
from sqlalchemy import Column, String, Text, DateTime, JSON
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class NotebookItemModel(Base):
    __tablename__ = "notebook_items"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), nullable=False)
    knowledge_id = Column(String(64), nullable=False)
    item_type = Column(String(32), nullable=False)  # 'summary' | 'note' | 'wrong_answer'
    content = Column(Text, nullable=False)
    extra_data = Column(JSON, nullable=True)        # 时间戳手记、错题解析等
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 3.4 后续升级至 PostgreSQL (pgvector) 的无痛纠正路径
当进入第二阶段需要 pgvector 向量检索与 PostgreSQL 生产环境时，只需要在配置中修改 `DATABASE_URL`：

```python
# PoC 开发环境 (SQLite)
# 默认由 code_navi.paths.application_data_dir() 生成当前机器的绝对路径；
# 也可以通过 CODE_NAVI_DATA_DIR 或 LEARNING_DATABASE_URL 覆盖。

# 生产/全量环境 (PostgreSQL)
# LEARNING_DATABASE_URL = "postgresql+psycopg2://user:password@db-host:5432/codenavi_db"
```
由于采用了 SQLAlchemy 统一模型，**上层 Service 与 API 路由逻辑不需要修改一行代码**！

---

## 四、 架构决策三：课后流转跳转契约 (Go 按钮双轮驱动传递)

### 4.1 决策内容
知识点学习完成后，跨 Tab / 跨模块跳转（代码练习 / 科研助手）采用 **“URL 关键 Query 参数 + Zustand 全局 Store 数据流”** 的双轮驱动契约。

### 4.2 契约数据接口定义 (`FlowPayload`)
```typescript
// lib/store/flow-store.ts
export interface FlowPayload {
  sessionId: string;
  masteredKnowledgePoint: {
    id: string;          // e.g. "kp_dhcp_4stage"
    name: string;        // e.g. "DHCP 四阶段报文交互"
  };
  studentPersona: 'academic' | 'software_coursework' | 'cross_disciplinary';
  targetModule: 'practice' | 'research';
  payloadData: {
    recommendedTopic?: string;    // 科研助手推荐课题
    exerciseIds?: string[];       // 代码练习推荐题目
  };
}
```

### 4.3 跳转与容错流转过程
```mermaid
sequenceDiagram
    autonumber
    participant LearnUI as 知识点学习页 (DownstreamGoCard)
    participant Store as Zustand (useFlowStore)
    participant TargetUI as 下游模块页 (/student/practice)
    participant API as 后端 API 服务

    LearnUI->>Store: 1. 写入完整 FlowPayload 对象
    LearnUI->>TargetUI: 2. Next.js router.push('/student/practice?knowledge_id=kp_dhcp&session_id=sess_123')
    
    alt 情况 A: 页面正常跳转 (Store 存在)
        TargetUI->>Store: 3a. 读取 FlowPayload，完成渲染
    else 情况 B: 用户刷新页面或直接访问 URL (Store 丢失)
        TargetUI->>API: 3b. 提取 URL Query (knowledge_id, session_id)，发起 API 补全请求
        API-->>TargetUI: 4b. 返回补充的上下文，完成渲染
    end
```

### 4.4 易于变动与纠正分析
* 若后续下游模块更改了入参数据字段，只需扩展 `FlowPayload` 接口定义，不破坏现有的 URL 导航机制。

---

## 五、 Cline / AI Vibecoding 落地执行 Checklists

AI 编程工具 (Cline / Antigravity) 可按顺序执行以下任务清单：

- [ ] **Task 1**: 在 `pyproject.toml` 中为 `[project.optional-dependencies]` 添加 `server = ["fastapi>=0.115", "uvicorn>=0.30", "sqlalchemy>=2.0"]`。
- [ ] **Task 2**: 创建 `src/code_navi/learning/router.py`，实现 `POST /api/v1/learning/explain` 端点。
- [ ] **Task 3**: 创建 `src/code_navi/server.py`，配置 FastAPI 主实例并引入 `learning_router`。
- [ ] **Task 4**: 在 `src/code_navi/learning/models.py` 定义基于 SQLAlchemy 的 `NotebookItemModel` 模型，实现本地 SQLite 读写。
- [ ] **Task 5**: 在前端组件中，落地基于 `FlowPayload` 的 Zustand + URL Query 组合跳转。

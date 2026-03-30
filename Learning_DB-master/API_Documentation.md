# Learning Management System API 文档

本API文档描述了学习管理系统的所有可用端点和功能。

## 基础信息
- **API 版本**: v1
- **基础 URL**: http://127.0.0.1:8000/api/v1
- **协议**: HTTPS/HTTP
- **内容类型**: application/json

## 数据模型

### UserInformation (用户信息)
- **id**: Integer (主键)
- **name**: String (最大长度 45)
- **email**: String (最大长度 45) (唯一)
- **password**: String (最大长度 45)
- **gender**: Enum ('male', 'female')
- **age**: Integer
- **current_subject**: String (最大长度 100)

### SourceDocument (源文档)
- **id**: Integer (主键)
- **user_id**: Integer (外键)
- **file_name**: String (最大长度 100)
- **file_path**: String (最大长度 100)
- **upload_date**: Date
- **processed_status**: Enum ('Pending', 'Done', 'Failed')

### DailyBrief (每日简报)
- **id**: Integer (主键)
- **user_id**: Integer (外键)
- **posterior_insight**: String (最大长度 100)
- **key_concepts**: Text
- **created_at**: DateTime
- **review_stage**: Integer
- **User_reflect**: Text
- **source_handouts**: String (最大长度 100)
- **origin**: Enum ('SC','PDF')
- **prompt_question**: Text

### EliteIdeaCard (精英想法卡片)
- **id**: Integer (主键)
- **daily_brief_id**: Integer (外键)
- **origin_concept**: String (最大长度 100)
- **meta_idea_name**: String (最大长度 100)
- **meta_explanation**: String (最大长度 100)
- **create_at**: DateTime

### EliteIdeaCase (精英想法案例)
- **id**: Integer (主键)
- **meta_id**: Integer (外键)
- **case_title**: String (最大长度 100)
- **case_content**: String (最大长度 100)
- **subject**: String (最大长度 100)
- **image_path**: String (最大长度 100)
- **query_rewrite**: Text

### ExternalResource (外部资源)
- **id**: Integer (主键)
- **card_id**: Integer (外键)
- **title**: String (最大长度 100)
- **url**: String (最大长度 100)
- **LLM_context**: Text
- **source**: String (最大长度 100)

### UserScreenshot (用户截图)
- **id**: Integer (主键)
- **user_id**: Integer (外键)
- **image_path**: String (最大长度 100)
- **vlm_analysis**: Text
- **upload_date**: Date

### AssociationBrief (关联简报)
- **id**: Integer (主键)
- **user_id**: Integer (外键)
- **content**: Text
- **notes_date**: Date
- **screenshot_date**: Date
- **created_at**: DateTime

### ScholarNote (学者笔记)
- **id**: Integer (主键)
- **user_id**: Integer (外键)
- **daily_brief_id**: Integer (外键)
- **note_title**: String (最大长度 100)
- **note_content**: Text
- **created_at**: DateTime
- **updated_at**: DateTime

### KnowledgeMap (知识图谱)
- **id**: Integer (主键)
- **user_id**: Integer (外键)
- **source_doc_id**: Integer (外键)
- **map_json**: JSON
- **created_at**: DateTime

### MapInteractionLog (图谱交互日志)
- **id**: Integer (主键)
- **user_id**: Integer (外键)
- **source_doc_id**: Integer (外键)
- **node_id**: String (最大长度 100)
- **user_query**: Text
- **ai_response**: Text
- **created_at**: DateTime
- **is_distilled**: Integer

### MapCognitiveSnapshot (图谱认知快照)
- **id**: Integer (主键)
- **user_id**: Integer (外键)
- **source_doc_id**: Integer (外键)
- **last_processed_log_id**: Integer
- **snapshot_content**: Text
- **path_nodes**: JSON
- **version**: Integer
- **last_log_id**: Integer

### AppUsageLog (应用使用日志)
- **id**: Integer (主键)
- **user_id**: Integer (外键)
- **start_time**: DateTime
- **end_time**: DateTime
- **duration_seconds**: Integer

## API 端点

### API端点列表

### 用户认证相关API
- **POST** `/register` - 用户注册
- **POST** `/login` - 用户登录

### App使用记录相关API
- **POST** `/app-usage` - 记录应用使用
- **GET** `/app-usage/stats/{user_id}` - 获取用户使用统计

### 用户信息相关API
- **POST** `/users` - 创建新用户
- **GET** `/users/{user_id}` - 获取特定用户信息
- **GET** `/users` - 获取所有用户列表
- **PUT** `/users/{user_id}` - 更新用户信息
- **DELETE** `/users/{user_id}` - 删除用户

### 源文档相关API
- **POST** `/source-documents` - 创建新源文档记录
- **GET** `/source-documents/{doc_id}` - 获取特定源文档
- **GET** `/source-documents` - 获取所有源文档列表
- **PUT** `/source-documents/{doc_id}` - 更新源文档信息
- **DELETE** `/source-documents/{doc_id}` - 删除源文档

### 文件上传相关API
- **POST** `/upload-pdf` - 上传PDF文件

### 每日简报相关API
- **POST** `/daily-briefs` - 创建新每日简报
- **GET** `/daily-briefs/{brief_id}` - 获取特定每日简报
- **GET** `/daily-briefs` - 获取所有每日简报列表
- **PUT** `/daily-briefs/{brief_id}` - 更新每日简报信息
- **DELETE** `/daily-briefs/{brief_id}` - 删除每日简报

### 精英想法卡片相关API
- **POST** `/elite-idea-cards` - 创建新精英想法卡片
- **GET** `/elite-idea-cards/{card_id}` - 获取特定精英想法卡片
- **GET** `/elite-idea-cards` - 获取所有精英想法卡片列表
- **PUT** `/elite-idea-cards/{card_id}` - 更新精英想法卡片信息
- **DELETE** `/elite-idea-cards/{card_id}` - 删除精英想法卡片

### 精英想法案例相关API
- **POST** `/elite-idea-cases` - 创建新精英想法案例
- **GET** `/elite-idea-cases/{case_id}` - 获取特定精英想法案例
- **GET** `/elite-idea-cases` - 获取所有精英想法案例列表
- **PUT** `/elite-idea-cases/{case_id}` - 更新精英想法案例信息
- **DELETE** `/elite-idea-cases/{case_id}` - 删除精英想法案例

### 外部资源相关API
- **POST** `/external-resources` - 创建新外部资源
- **GET** `/external-resources/{resource_id}` - 获取特定外部资源
- **GET** `/external-resources` - 获取所有外部资源列表
- **PUT** `/external-resources/{resource_id}` - 更新外部资源信息
- **DELETE** `/external-resources/{resource_id}` - 删除外部资源

### 用户截图相关API
- **POST** `/user-screenshots` - 创建新用户截图
- **GET** `/user-screenshots/{screenshot_id}` - 获取特定用户截图
- **GET** `/user-screenshots` - 获取所有用户截图列表
- **PUT** `/user-screenshots/{screenshot_id}` - 更新用户截图信息
- **DELETE** `/user-screenshots/{screenshot_id}` - 删除用户截图

### 关联简报相关API
- **POST** `/association-briefs` - 创建新关联简报
- **GET** `/association-briefs/{brief_id}` - 获取特定关联简报
- **GET** `/association-briefs` - 获取所有关联简报列表
- **PUT** `/association-briefs/{brief_id}` - 更新关联简报信息
- **DELETE** `/association-briefs/{brief_id}` - 删除关联简报

### 学者笔记相关API
- **POST** `/scholar-notes` - 创建新学者笔记
- **GET** `/scholar-notes/{note_id}` - 获取特定学者笔记
- **GET** `/scholar-notes` - 获取所有学者笔记列表
- **PUT** `/scholar-notes/{note_id}` - 更新学者笔记信息
- **DELETE** `/scholar-notes/{note_id}` - 删除学者笔记

### 知识图谱相关API
- **POST** `/knowledge-maps` - 创建新知识图谱
- **GET** `/knowledge-maps/{km_id}` - 获取特定知识图谱
- **GET** `/knowledge-maps` - 获取所有知识图谱列表
- **PUT** `/knowledge-maps/{km_id}` - 更新知识图谱信息
- **DELETE** `/knowledge-maps/{km_id}` - 删除知识图谱

### 图谱交互日志相关API
- **POST** `/map-interaction-logs` - 创建新图谱交互日志
- **GET** `/map-interaction-logs/{log_id}` - 获取特定图谱交互日志
- **GET** `/map-interaction-logs` - 获取所有图谱交互日志列表
- **PUT** `/map-interaction-logs/{log_id}` - 更新图谱交互日志信息
- **DELETE** `/map-interaction-logs/{log_id}` - 删除图谱交互日志

### 图谱认知快照相关API
- **POST** `/map-cognitive-snapshots` - 创建新图谱认知快照
- **GET** `/map-cognitive-snapshots/{snapshot_id}` - 获取特定图谱认知快照
- **GET** `/map-cognitive-snapshots` - 获取所有图谱认知快照列表
- **PUT** `/map-cognitive-snapshots/{snapshot_id}` - 更新图谱认知快照信息
- **DELETE** `/map-cognitive-snapshots/{snapshot_id}` - 删除图谱认知快照

### 文件上传管理

#### 上传PDF文件
- **POST** `/upload-pdf`
- **参数**: 
  - `file`: PDF文件 (表单数据, 必需)
  - `user_email`: 用户邮箱 (查询参数, 可选) - 如果提供，将从用户表中查找对应用户
- **请求示例**:
  ```bash
  curl -X POST "http://127.0.0.1:8000/api/v1/upload-pdf?user_email=user@example.com" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf"
  ```
- **响应**: 
  ```json
  {
    "id": 1,
    "user_id": 1,
    "file_name": "document.pdf",
    "file_path": "uploads/uuid_document.pdf",
    "upload_date": "2023-10-01",
    "processed_status": "Pending"
  }
  ```
- **错误响应**:
  - `400 Bad Request`: 文件类型不是PDF
  - `404 Not Found`: 用户不存在

### 用户认证管理

#### 用户注册
- **POST** `/register`
- **请求体**: 
  ```json
  {
    "email": "user@example.com",
    "password": "password123",
    "name": "张三",
    "gender": "male",
    "age": 25,
    "current_subject": "计算机科学"
  }
  ```
- **响应**: 
  ```json
  {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "message": "注册成功",
    "code": 200
  }
  ```
- **错误响应**:
  - `400 Bad Request`: 邮箱已被注册

#### 用户登录
- **POST** `/login`
- **请求体**: 
  ```json
  {
    "email": "user@example.com",
    "password": "password123"
  }
  ```
- **响应**: 
  ```json
  {
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "message": "登录成功",
    "code": 200,
    "user_id": 1
  }
  ```
- **错误响应**:
  - `401 Unauthorized`: 账号或密码错误

### App使用记录管理

#### 记录应用使用
- **POST** `/app-usage`
- **请求体**: 
  ```json
  {
    "user_id": 1,
    "start_time": "2023-10-01T10:00:00",
    "end_time": "2023-10-01T11:00:00",
    "duration_seconds": 3600
  }
  ```
- **响应**: 创建的应用使用记录对象

#### 获取用户使用统计
- **GET** `/app-usage/stats/{user_id}`
- **参数**: `user_id` (路径参数)
- **响应**: 
  ```json
  {
    "data_points": [0.0, 0.0, ..., 60.0, ...]  // 24小时的使用分钟数
  }
  ```

### 用户信息管理

#### 获取所有用户
- **GET** `/users`
- **参数**: `skip` (可选, 默认0), `limit` (可选, 默认100)
- **响应**: 用户对象列表

#### 获取特定用户
- **GET** `/users/{user_id}`
- **参数**: `user_id` (路径参数)
- **响应**: 用户对象

#### 创建用户
- **POST** `/users`
- **请求体**: 
  ```json
  {
    "name": "张三",
    "email": "zhangsan@example.com",
    "password": "password123",
    "gender": "male",
    "age": 25,
    "current_subject": "计算机科学"
  }
  ```
- **响应**: 创建的用户对象

#### 更新用户
- **PUT** `/users/{user_id}`
- **参数**: `user_id` (路径参数)
- **请求体**: 
  ```json
  {
    "name": "李四",
    "email": "lisi@example.com",
    "gender": "female",
    "age": 30,
    "current_subject": "数学"
  }
  ```
- **响应**: 更新的用户对象

#### 删除用户
- **DELETE** `/users/{user_id}`
- **参数**: `user_id` (路径参数)
- **响应**: 成功消息

### 源文档管理

#### 获取所有源文档
- **GET** `/source-documents`
- **参数**: `skip` (可选, 默认0), `limit` (可选, 默认100)
- **响应**: 源文档对象列表

#### 获取特定源文档
- **GET** `/source-documents/{doc_id}`
- **参数**: `doc_id` (路径参数)
- **响应**: 源文档对象

#### 创建源文档
- **POST** `/source-documents`
- **请求体**: 
  ```json
  {
    "user_id": 1,
    "file_name": "example.pdf",
    "file_path": "/path/to/file",
    "upload_date": "2023-10-01",
    "processed_status": "Pending"
  }
  ```
- **响应**: 创建的源文档对象

#### 更新源文档
- **PUT** `/source-documents/{doc_id}`
- **参数**: `doc_id` (路径参数)
- **请求体**: 
  ```json
  {
    "file_name": "updated_example.pdf",
    "file_path": "/path/to/updated_file",
    "processed_status": "Done"
  }
  ```
- **响应**: 更新的源文档对象

#### 删除源文档
- **DELETE** `/source-documents/{doc_id}`
- **参数**: `doc_id` (路径参数)
- **响应**: 成功消息

### 每日简报管理

#### 获取所有每日简报
- **GET** `/daily-briefs`
- **参数**: `skip` (可选, 默认0), `limit` (可选, 默认100)
- **响应**: 每日简报对象列表

#### 获取特定每日简报
- **GET** `/daily-briefs/{brief_id}`
- **参数**: `brief_id` (路径参数)
- **响应**: 每日简报对象

#### 创建每日简报
- **POST** `/daily-briefs`
- **请求体**: 
  ```json
  {
    "user_id": 1,
    "posterior_insight": "今日学习洞察",
    "key_concepts": "关键概念总结...",
    "review_stage": 1,
    "User_reflect": "个人反思...",
    "source_handouts": "讲义来源",
    "origin": "PDF"
  }
  ```
- **响应**: 创建的每日简报对象

#### 更新每日简报
- **PUT** `/daily-briefs/{brief_id}`
- **参数**: `brief_id` (路径参数)
- **请求体**: 
  ```json
  {
    "posterior_insight": "更新的学习洞察",
    "key_concepts": "更新的关键概念"
  }
  ```
- **响应**: 更新的每日简报对象

#### 删除每日简报
- **DELETE** `/daily-briefs/{brief_id}`
- **参数**: `brief_id` (路径参数)
- **响应**: 成功消息



### 精英想法卡片管理

#### 获取所有精英想法卡片
- **GET** `/elite-idea-cards`
- **参数**: `skip` (可选, 默认0), `limit` (可选, 默认100)
- **响应**: 精英想法卡片对象列表

#### 获取特定精英想法卡片
- **GET** `/elite-idea-cards/{card_id}`
- **参数**: `card_id` (路径参数)
- **响应**: 精英想法卡片对象

#### 创建精英想法卡片
- **POST** `/elite-idea-cards`
- **请求体**: 
  ```json
  {
    "daily_brief_id": 1,
    "origin_concept": "原始概念",
    "meta_idea_name": "元想法名称",
    "meta_explanation": "元想法解释"
  }
  ```
- **响应**: 创建的精英想法卡片对象

#### 更新精英想法卡片
- **PUT** `/elite-idea-cards/{card_id}`
- **参数**: `card_id` (路径参数)
- **请求体**: 
  ```json
  {
    "meta_idea_name": "更新的想法名称",
    "meta_explanation": "更新的想法解释"
  }
  ```
- **响应**: 更新的精英想法卡片对象

#### 删除精英想法卡片
- **DELETE** `/elite-idea-cards/{card_id}`
- **参数**: `card_id` (路径参数)
- **响应**: 成功消息

### 精英想法案例管理

#### 获取所有精英想法案例
- **GET** `/elite-idea-cases`
- **参数**: `skip` (可选, 默认0), `limit` (可选, 默认100)
- **响应**: 精英想法案例对象列表

#### 获取特定精英想法案例
- **GET** `/elite-idea-cases/{case_id}`
- **参数**: `case_id` (路径参数)
- **响应**: 精英想法案例对象

#### 创建精英想法案例
- **POST** `/elite-idea-cases`
- **请求体**: 
  ```json
  {
    "meta_id": 1,
    "case_title": "优秀案例",
    "case_content": "这是一个优秀的案例...",
    "subject": "学科",
    "image_path": "/path/to/image.jpg",
    "query_rewrite": "重写查询..."
  }
  ```
- **响应**: 创建的精英想法案例对象

#### 更新精英想法案例
- **PUT** `/elite-idea-cases/{case_id}`
- **参数**: `case_id` (路径参数)
- **请求体**: 
  ```json
  {
    "case_title": "更新的案例标题",
    "case_content": "更新的案例内容"
  }
  ```
- **响应**: 更新的精英想法案例对象

#### 删除精英想法案例
- **DELETE** `/elite-idea-cases/{case_id}`
- **参数**: `case_id` (路径参数)
- **响应**: 成功消息

### 外部资源管理

#### 获取所有外部资源
- **GET** `/external-resources`
- **参数**: `skip` (可选, 默认0), `limit` (可选, 默认100)
- **响应**: 外部资源对象列表

#### 获取特定外部资源
- **GET** `/external-resources/{resource_id}`
- **参数**: `resource_id` (路径参数)
- **响应**: 外部资源对象

#### 创建外部资源
- **POST** `/external-resources`
- **请求体**: 
  ```json
  {
    "card_id": 1,
    "title": "优质资源",
    "url": "https://example.com",
    "LLM_context": "LLM上下文信息...",
    "source": "学习资料"
  }
  ```
- **响应**: 创建的外部资源对象

#### 更新外部资源
- **PUT** `/external-resources/{resource_id}`
- **参数**: `resource_id` (路径参数)
- **请求体**: 
  ```json
  {
    "title": "更新的资源标题",
    "LLM_context": "更新的上下文信息"
  }
  ```
- **响应**: 更新的外部资源对象

#### 删除外部资源
- **DELETE** `/external-resources/{resource_id}`
- **参数**: `resource_id` (路径参数)
- **响应**: 成功消息

### 用户截图管理

#### 获取所有用户截图
- **GET** `/user-screenshots`
- **参数**: `skip` (可选, 默认0), `limit` (可选, 默认100)
- **响应**: 用户截图对象列表

#### 获取特定用户截图
- **GET** `/user-screenshots/{screenshot_id}`
- **参数**: `screenshot_id` (路径参数)
- **响应**: 用户截图对象

#### 创建用户截图
- **POST** `/user-screenshots`
- **请求体**: 
  ```json
  {
    "user_id": 1,
    "image_path": "/path/to/screenshot.png",
    "vlm_analysis": "VLM分析结果...",
    "upload_date": "2023-10-01"
  }
  ```
- **响应**: 创建的用户截图对象

#### 更新用户截图
- **PUT** `/user-screenshots/{screenshot_id}`
- **参数**: `screenshot_id` (路径参数)
- **请求体**: 
  ```json
  {
    "image_path": "/path/to/new_screenshot.png",
    "vlm_analysis": "更新的VLM分析结果..."
  }
  ```
- **响应**: 更新的用户截图对象

#### 删除用户截图
- **DELETE** `/user-screenshots/{screenshot_id}`
- **参数**: `screenshot_id` (路径参数)
- **响应**: 成功消息

### 关联简报管理

#### 获取所有关联简报
- **GET** `/association-briefs`
- **参数**: `skip` (可选, 默认0), `limit` (可选, 默认100)
- **响应**: 关联简报对象列表

#### 获取特定关联简报
- **GET** `/association-briefs/{brief_id}`
- **参数**: `brief_id` (路径参数)
- **响应**: 关联简报对象

#### 创建关联简报
- **POST** `/association-briefs`
- **请求体**: 
  ```json
  {
    "user_id": 1,
    "content": "这是一个关联简报...",
    "notes_date": "2023-10-01",
    "screenshot_date": "2023-10-01"
  }
  ```
- **响应**: 创建的关联简报对象

#### 更新关联简报
- **PUT** `/association-briefs/{brief_id}`
- **参数**: `brief_id` (路径参数)
- **请求体**: 
  ```json
  {
    "content": "更新的简报内容"
  }
  ```
- **响应**: 更新的关联简报对象

#### 删除关联简报
- **DELETE** `/association-briefs/{brief_id}`
- **参数**: `brief_id` (路径参数)
- **响应**: 成功消息

### 学者笔记管理

#### 获取所有学者笔记
- **GET** `/scholar-notes`
- **参数**: `skip` (可选, 默认0), `limit` (可选, 默认100)
- **响应**: 学者笔记对象列表

#### 获取特定学者笔记
- **GET** `/scholar-notes/{note_id}`
- **参数**: `note_id` (路径参数)
- **响应**: 学者笔记对象

#### 创建学者笔记
- **POST** `/scholar-notes`
- **请求体**: 
  ```json
  {
    "user_id": 1,
    "daily_brief_id": 1,
    "note_title": "学术笔记",
    "note_content": "这是学术笔记内容..."
  }
  ```
- **响应**: 创建的学者笔记对象

#### 更新学者笔记
- **PUT** `/scholar-notes/{note_id}`
- **参数**: `note_id` (路径参数)
- **请求体**: 
  ```json
  {
    "note_title": "更新的笔记标题",
    "note_content": "更新的笔记内容"
  }
  ```
- **响应**: 更新的学者笔记对象

#### 删除学者笔记
- **DELETE** `/scholar-notes/{note_id}`
- **参数**: `note_id` (路径参数)
- **响应**: 成功消息

### 知识图谱管理

#### 获取所有知识图谱
- **GET** `/knowledge-maps`
- **参数**: `skip` (可选, 默认0), `limit` (可选, 默认100)
- **响应**: 知识图谱对象列表

#### 获取特定知识图谱
- **GET** `/knowledge-maps/{km_id}`
- **参数**: `km_id` (路径参数)
- **响应**: 知识图谱对象

#### 创建知识图谱
- **POST** `/knowledge-maps`
- **请求体**: 
  ```json
  {
    "user_id": 1,
    "source_doc_id": 1,
    "map_json": {"nodes": [], "edges": []}
  }
  ```
- **响应**: 创建的知识图谱对象

#### 更新知识图谱
- **PUT** `/knowledge-maps/{km_id}`
- **参数**: `km_id` (路径参数)
- **请求体**: 
  ```json
  {
    "map_json": {"nodes": [{"id": 1, "label": "新节点"}], "edges": []}
  }
  ```
- **响应**: 更新的知识图谱对象

#### 删除知识图谱
- **DELETE** `/knowledge-maps/{km_id}`
- **参数**: `km_id` (路径参数)
- **响应**: 成功消息

### 图谱交互日志管理

#### 获取所有图谱交互日志
- **GET** `/map-interaction-logs`
- **参数**: `skip` (可选, 默认0), `limit` (可选, 默认100)
- **响应**: 图谱交互日志对象列表

#### 获取特定图谱交互日志
- **GET** `/map-interaction-logs/{log_id}`
- **参数**: `log_id` (路径参数)
- **响应**: 图谱交互日志对象

#### 创建图谱交互日志
- **POST** `/map-interaction-logs`
- **请求体**: 
  ```json
  {
    "user_id": 1,
    "source_doc_id": 2,
    "node_id": "node_1",
    "user_query": "用户查询内容...",
    "ai_response": "AI响应内容...",
    "is_distilled": 0
  }
  ```
- **响应**: 创建的图谱交互日志对象

#### 更新图谱交互日志
- **PUT** `/map-interaction-logs/{log_id}`
- **参数**: `log_id` (路径参数)
- **请求体**: 
  ```json
  {
    "is_distilled": 1
  }
  ```
- **响应**: 更新的图谱交互日志对象

#### 删除图谱交互日志
- **DELETE** `/map-interaction-logs/{log_id}`
- **参数**: `log_id` (路径参数)
- **响应**: 成功消息

### 图谱认知快照管理

#### 获取所有图谱认知快照
- **GET** `/map-cognitive-snapshots`
- **参数**: `skip` (可选, 默认0), `limit` (可选, 默认100)
- **响应**: 图谱认知快照对象列表

#### 获取特定图谱认知快照
- **GET** `/map-cognitive-snapshots/{snapshot_id}`
- **参数**: `snapshot_id` (路径参数)
- **响应**: 图谱认知快照对象

#### 创建图谱认知快照
- **POST** `/map-cognitive-snapshots`
- **请求体**: 
  ```json
  {
    "user_id": 1,
    "source_doc_id": 2,
    "last_processed_log_id": 1,
    "snapshot_content": "快照内容...",
    "path_nodes": ["node1", "node2"],
    "version": 1
  }
  ```
- **响应**: 创建的图谱认知快照对象

#### 更新图谱认知快照
- **PUT** `/map-cognitive-snapshots/{snapshot_id}`
- **参数**: `snapshot_id` (路径参数)
- **请求体**: 
  ```json
  {
    "snapshot_content": "更新的快照内容...",
    "path_nodes": ["node1", "node3"]
  }
  ```
- **响应**: 更新的图谱认知快照对象

#### 删除图谱认知快照
- **DELETE** `/map-cognitive-snapshots/{snapshot_id}`
- **参数**: `snapshot_id` (路径参数)
- **响应**: 成功消息

## 错误处理

API可能返回以下HTTP状态码：

- **200**: 请求成功
- **201**: 资源创建成功
- **400**: 请求参数错误
- **404**: 资源未找到
- **500**: 服务器内部错误

## 认证

API 使用 JWT (JSON Web Token) 进行身份验证。用户需要通过 `/register` 或 `/login` 端点获取访问令牌，然后在后续请求的 Authorization 头中包含该令牌。

**示例请求头**:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

如果令牌无效或过期，API 将返回 401 Unauthorized 错误。

## 注意事项

1. 所有日期时间格式遵循ISO 8601标准
2. 所有文本字段应避免SQL注入和XSS攻击
3. 文件上传功能需要额外的安全验证
4. 在生产环境中应启用HTTPS
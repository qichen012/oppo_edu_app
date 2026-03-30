from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, Enum, Text, ForeignKey, JSON, Boolean
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os
from dotenv import load_dotenv

load_dotenv()  # 加载 .env 文件

DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:password@localhost:3306/Learning_DB")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 用户信息表
class UserInformation(Base):
    __tablename__ = "user_information"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(45))
    email = Column(String(45), unique=True, index=True)#邮箱
    password = Column(String(255))#密码（bcrypt hash 长度约 60）
    gender = Column(Enum('male', 'female'))
    age = Column(Integer)
    current_subject = Column(String(100))
    
    # 关系
    source_documents = relationship("SourceDocument", back_populates="user")
    daily_briefs = relationship("DailyBrief", back_populates="user")
    user_screenshots = relationship("UserScreenshot", back_populates="user")
    association_briefs = relationship("AssociationBrief", back_populates="user")
    scholar_notes = relationship("ScholarNote", back_populates="user")
    knowledge_maps = relationship("KnowledgeMap", back_populates="user")
    map_interaction_logs = relationship("MapInteractionLog", back_populates="user")
    map_cognitive_snapshots = relationship("MapCognitiveSnapshot", back_populates="user")

# 源文档表
class SourceDocument(Base):
    __tablename__ = "source_documents"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_information.id"))
    file_name = Column(String(100))
    file_path = Column(String(100))
    upload_date = Column(Date, nullable=False)
    processed_status = Column(Enum('Pending', 'Done', 'Failed'), nullable=False)
    
    # 关系
    user = relationship("UserInformation", back_populates="source_documents")
    knowledge_maps = relationship("KnowledgeMap", back_populates="source_document")
    map_interaction_logs = relationship("MapInteractionLog", back_populates="source_document")
    map_cognitive_snapshots = relationship("MapCognitiveSnapshot", back_populates="source_document")

# 每日简报表
class DailyBrief(Base):
    __tablename__ = "daily_briefs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_information.id"))
    posterior_insight = Column(String(100))
    key_concepts = Column(Text(100))
    created_at = Column(DateTime)
    review_stage = Column(Integer)
    User_reflect = Column(Text(100))
    source_handouts = Column(String(100))
    origin = Column(Enum('SC','PDF'))
    prompt_question = Column(Text(100))
    
    # 关系
    user = relationship("UserInformation", back_populates="daily_briefs")
    elite_idea_cards = relationship("EliteIdeaCard", back_populates="daily_brief")
    scholar_notes = relationship("ScholarNote", back_populates="daily_brief")


# 精英想法卡片表
class EliteIdeaCard(Base):
    __tablename__ = "elite_idea_cards"
    
    id = Column(Integer, primary_key=True, index=True)
    daily_brief_id = Column(Integer, ForeignKey("daily_briefs.id"))
    origin_concept = Column(String(100)) # 暂时没有用
    meta_idea_name = Column(String(100))
    meta_explanation = Column(String(100))
    create_at = Column(DateTime)
    
    # 关系
    daily_brief = relationship("DailyBrief", back_populates="elite_idea_cards")
    elite_idea_cases = relationship("EliteIdeaCase", back_populates="elite_idea_card")
    external_resources = relationship("ExternalResource", back_populates="elite_idea_card")

# 精英想法案例表
class EliteIdeaCase(Base):
    __tablename__ = "elite_idea_cases"
    
    id = Column(Integer, primary_key=True, index=True)
    meta_id = Column(Integer, ForeignKey("elite_idea_cards.id"))
    case_title = Column(String(100))
    case_content = Column(String(100))
    image_path = Column(String(100))
    query_rewrite = Column(Text(100))
    
    # 关系
    elite_idea_card = relationship("EliteIdeaCard", back_populates="elite_idea_cases")

# 外部资源表
class ExternalResource(Base):
    __tablename__ = "external_resources"
    
    id = Column(Integer, primary_key=True, index=True)
    card_id = Column(Integer, ForeignKey("elite_idea_cards.id"))
    title = Column(String(100))
    url = Column(String(100))
    LLM_context = Column(Text(100))
    source = Column(String(100))
    
    # 关系
    elite_idea_card = relationship("EliteIdeaCard", back_populates="external_resources")

# 用户截图表
class UserScreenshot(Base):
    __tablename__ = "user_screenshots"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_information.id"))
    image_path = Column(String(100))
    vlm_analysis = Column(Text(100))
    upload_date = Column(Date)
    
    # 关系
    user = relationship("UserInformation", back_populates="user_screenshots")

# 关联简报表
class AssociationBrief(Base):
    __tablename__ = "association_briefs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_information.id"))
    content = Column(Text(100))
    notes_date = Column(DateTime, ForeignKey("daily_briefs.created_at"))
    screenshot_date = Column(Date, ForeignKey("user_screenshots.upload_date"))
    created_at = Column(DateTime)
    
    # 关系
    user = relationship("UserInformation", back_populates="association_briefs")


# 知识图谱表
class KnowledgeMap(Base):
    __tablename__ = "knowledge_maps"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_information.id"))
    source_doc_id = Column(Integer, ForeignKey("source_documents.id"))
    map_json = Column(JSON)
    created_at = Column(DateTime)
    
    # 关系
    user = relationship("UserInformation", back_populates="knowledge_maps")
    source_document = relationship("SourceDocument", back_populates="knowledge_maps")

# 图谱交互日志表
class MapInteractionLog(Base):
    __tablename__ = "map_interaction_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_information.id"))
    source_doc_id = Column(Integer, ForeignKey("source_documents.id"))
    node_id = Column(String(100))
    user_query = Column(Text(100))
    ai_response = Column(Text(100))
    created_at = Column(DateTime)
    is_distilled = Column(Integer)
    
    # 关系
    user = relationship("UserInformation", back_populates="map_interaction_logs")
    source_document = relationship("SourceDocument", back_populates="map_interaction_logs")

# 学者笔记表
class ScholarNote(Base):
    __tablename__ = "scholar_notes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_information.id"))
    daily_brief_id = Column(Integer, ForeignKey("daily_briefs.id"))
    note_title = Column(String(100))
    note_content = Column(Text(100))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    
    # 关系
    user = relationship("UserInformation", back_populates="scholar_notes")
    daily_brief = relationship("DailyBrief", back_populates="scholar_notes")


# 图谱认知快照表
class MapCognitiveSnapshot(Base):
    __tablename__ = "map_cognitive_snapshots"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user_information.id"))
    source_doc_id = Column(Integer, ForeignKey("source_documents.id"))
    last_processed_log_id = Column(Integer)
    snapshot_content = Column(Text(100))
    path_nodes = Column(JSON)
    version = Column(Integer)
    last_log_id = Column(Integer)
    
    # 关系
    user = relationship("UserInformation", back_populates="map_cognitive_snapshots")
    source_document = relationship("SourceDocument", back_populates="map_cognitive_snapshots")


class AppUsageLog(Base):
    __tablename__ = "app_usage_logs"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user_information.id"))
    start_time = Column(DateTime)          # 本次打开 App 的时间
    end_time = Column(DateTime)            # 本次离开 App 的时间
    duration_seconds = Column(Integer)     # 使用时长（秒）
    
    # 关系
    user = relationship("UserInformation")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
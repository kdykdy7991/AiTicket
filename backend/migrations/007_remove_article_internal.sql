-- 移除 articles 表的 internal 字段及 internal_note 类型
BEGIN;

-- 删除所有内部备注记录
DELETE FROM articles WHERE internal = TRUE OR type = 'internal_note';

-- 移除内部备注相关约束
ALTER TABLE articles DROP CONSTRAINT IF EXISTS chk_internal_note;
ALTER TABLE articles DROP CONSTRAINT IF EXISTS chk_article_type;

-- 删除 internal 字段
ALTER TABLE articles DROP COLUMN IF EXISTS internal;

-- 重建 article 类型约束，只保留 reply / addition / reminder
ALTER TABLE articles
    ADD CONSTRAINT chk_article_type CHECK (type IN ('reply', 'addition', 'reminder'));

COMMIT;

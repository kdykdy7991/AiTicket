-- ============================================================
-- 重置所有表的主键序列到各自 max(id)
--
-- 背景：种子/迁移脚本用显式 id 插入数据时，自增序列不会跟随推进，
-- 后续靠序列自增 INSERT 会撞主键（duplicate key ... already exists）。
-- 本脚本幂等、可重复执行，恢复库 / 导入数据后跑一次即可修复全部表。
-- ============================================================

DO $$
DECLARE
    r RECORD;
    maxv BIGINT;
BEGIN
    FOR r IN
        SELECT seq.relname AS seq_name,
               tbl.relname AS table_name,
               att.attname AS column_name
        FROM pg_class seq
        JOIN pg_namespace ns ON ns.oid = seq.relnamespace
        JOIN pg_depend dep ON dep.objid = seq.oid AND dep.deptype IN ('a','i')
        JOIN pg_class tbl ON tbl.oid = dep.refobjid
        JOIN pg_attribute att ON att.attrelid = tbl.oid AND att.attnum = dep.refobjsubid
        WHERE seq.relkind = 'S' AND ns.nspname = 'public'
    LOOP
        EXECUTE format('SELECT COALESCE(MAX(%I), 0) FROM %I', r.column_name, r.table_name) INTO maxv;
        IF maxv > 0 THEN
            PERFORM setval(r.seq_name::regclass, maxv, true);   -- 下次 nextval = maxv + 1
        ELSE
            PERFORM setval(r.seq_name::regclass, 1, false);     -- 空表：下次 nextval = 1
        END IF;
        RAISE NOTICE 'reset %  <-  % = %', r.seq_name, r.table_name, maxv;
    END LOOP;
END $$;

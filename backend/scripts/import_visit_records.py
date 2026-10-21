"""Import the two data sheets of 来电登记表.xlsx into independent visit records.

Usage:
    uv run python scripts/import_visit_records.py /path/to/来电登记表.xlsx --dry-run
    uv run python scripts/import_visit_records.py /path/to/来电登记表.xlsx

Source sheet + physical row is the idempotency key. No tickets are created.
"""

import argparse
import asyncio
import sys
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import async_session  # noqa: E402
from app.models.visit_record import VisitRecord  # noqa: E402


NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
LOCAL_TZ = timezone(timedelta(hours=8))
SHEETS = {"400客服热线": "xl/worksheets/sheet1.xml", "在线客服": "xl/worksheets/sheet2.xml"}
EXTRA_FIELDS = {
    "序号": "source_order", "客户来源": "customer_source", "性别": "gender",
    "客户分类": "customer_type", "公司名称": "company_name",
    "是否有效电话": "valid_contact", "事件等级": "priority", "客户诉求": "request",
    "对接部门": "department", "对接人": "liaison", "处理人": "handler",
    "处理详情": "handling_detail", "是否回访": "callback_status",
    "回访时间": "callback_time", "回访详情": "callback_detail",
    "是否退回处理": "returned", "是否闭环": "closed", "满意度": "satisfaction",
    "备注": "notes",
}


def _column(address: str) -> str:
    return "".join(char for char in address if char.isalpha())


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value if value and value != "-" else None


def _excel_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return (datetime(1899, 12, 30, tzinfo=LOCAL_TZ)
                + timedelta(days=float(value))).replace(microsecond=0)
    except ValueError:
        return None


def _read_rows(archive: zipfile.ZipFile, path: str, strings: list[str]):
    root = ET.fromstring(archive.read(path))
    for row in root.findall("m:sheetData/m:row", NS):
        values = {}
        for cell in row.findall("m:c", NS):
            raw = cell.findtext("m:v", default=None, namespaces=NS)
            if cell.get("t") == "s" and raw is not None:
                raw = strings[int(raw)]
            elif cell.get("t") == "inlineStr":
                raw = "".join(part.text or "" for part in cell.findall(".//m:t", NS))
            if raw is not None:
                values[_column(cell.get("r", ""))] = raw
        yield int(row.get("r", "0")), values


def parse_workbook(path: Path) -> list[dict]:
    records = []
    with zipfile.ZipFile(path) as archive:
        strings_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        strings = ["".join(part.text or "" for part in item.findall(".//m:t", NS))
                   for item in strings_root.findall("m:si", NS)]
        for sheet, xml_path in SHEETS.items():
            rows = iter(_read_rows(archive, xml_path, strings))
            _, header = next(rows)
            for row_number, values in rows:
                if not _clean(values.get("A")):
                    continue
                source = {label: _clean(values.get(column)) for column, label in header.items()}
                contact_at = _excel_time(source.get("来电时间") or source.get("联系时间"))
                if contact_at is None:
                    raise ValueError(f"{sheet} 第 {row_number} 行的联系时间无效")
                registered = source.get("是否登记工单")
                if registered not in ("是", "否"):
                    raise ValueError(f"{sheet} 第 {row_number} 行的是否登记工单无效")
                fields = {key: source[label] for label, key in EXTRA_FIELDS.items()
                          if source.get(label) is not None}
                closed_at = _excel_time(source.get("闭环时间"))
                if closed_at:
                    fields["closed_at"] = closed_at.isoformat()
                elif source.get("闭环时间"):
                    fields["closed_at"] = source["闭环时间"]
                records.append({
                    "source_sheet": sheet, "source_row": row_number,
                    "contact_at": contact_at,
                    "contact_number": source.get("来电号码") or source.get("联系号码"),
                    "customer_name": source.get("姓名"),
                    "service_agent": source.get("接待客服"),
                    "channel": sheet,
                    "category_l1": source.get("一级分类"),
                    "category_l2": source.get("二级分类"),
                    "registered_ticket": registered == "是",
                    "fields": fields,
                })
    return records


async def import_records(records: list[dict]) -> tuple[int, int]:
    inserted = skipped = 0
    async with async_session() as session:
        existing = set((await session.execute(
            select(VisitRecord.source_sheet, VisitRecord.source_row).where(
                VisitRecord.source_sheet.in_(SHEETS))
        )).all())
        for values in records:
            key = (values["source_sheet"], values["source_row"])
            if key in existing:
                skipped += 1
                continue
            session.add(VisitRecord(**values))
            inserted += 1
        await session.commit()
    return inserted, skipped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    records = parse_workbook(args.workbook)
    print(f"Parsed {len(records)} records: {dict(Counter(r['source_sheet'] for r in records))}")
    print(f"Registered-ticket flags: {dict(Counter(r['registered_ticket'] for r in records))}")
    if not args.dry_run:
        inserted, skipped = asyncio.run(import_records(records))
        print(f"Inserted {inserted}, skipped existing {skipped}")


if __name__ == "__main__":
    main()

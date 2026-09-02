"""Conservative, evidence-first GOODS facts from every text-bearing document."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

_STANDARD = re.compile(r"\b(?:ГОСТ(?:\s*Р)?|ТУ|ТР\s*ТС|ISO|IEC|DIN|СП|СНиП)\s*[№N]?\s*[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9./-]*", re.IGNORECASE)
_QUANTITY = re.compile(r"\b(?:количество|кол-во|объем)\s*[:—-]?\s*(\d+(?:[.,]\d+)?)\s*(шт\.?|штук|ед\.?|м|мм|кг|л|компл(?:ект)?(?:а)?|упак(?:овка)?(?:и)?)\b", re.IGNORECASE)
_CHARACTERISTIC = re.compile(r"\b(номинальное напряжение|напряжение|ёмкость|емкость|мощность|степень защиты|сечение|длина|ширина|высота|объем)\s*[:—-]?\s*(IP\s*\d{2,3}|\d+(?:[.,]\d+)?\s*(?:В|кВт|Ач|А|мм²|мм2|мм|см|м|ТБ|ГБ|кг|л))\b", re.IGNORECASE)
_DELIVERY = re.compile(r"\b(?:срок поставки|поставка)\s*[:—-]?\s*(?:в течение\s+)?\d+\s+(?:календарных?|рабочих?)\s+дн(?:я|ей)\b", re.IGNORECASE)
_PLACE = re.compile(r"\bместо поставки\s*[:—-]?\s*(.{8,220})", re.IGNORECASE)
_WARRANTY = re.compile(r"\b(?:гарантийн\w*\s+(?:срок|обязательств\w*)|гарантия)\b.{0,120}?\b(?:не менее\s+)?\d+\s+(?:месяц(?:ев|а)?|лет|года?)\b", re.IGNORECASE)
_PRODUCT = re.compile(r"\b(?:наименование (?:поставляемого )?товара|товар)\s*[:—-]\s*([^\n]{3,240})", re.IGNORECASE)
_UNIT = re.compile(r"^(шт\.?|штук|ед\.?|м|мм|кг|л|компл(?:ект)?(?:а)?|упак(?:овка)?(?:и)?)$", re.IGNORECASE)


@dataclass(frozen=True)
class ProcurementSourceFact:
    fact_id: str
    fact_type: str
    normalized_key: str
    value: str
    unit: str | None
    text: str
    source_document: str
    file_id: str
    semantic_role: str
    locator: str
    excerpt: str
    confidence: str
    extraction_strategy: str
    source_row_number: int | None = None


def semantic_procurement_role(document: Any) -> str:
    name = str(getattr(document, "display_name", "")).lower()
    text = str(getattr(document, "text", "") or "").lower()
    sample = f"{name}\n{text[:12000]}"
    if any(marker in sample for marker in ("обоснование нмцк", "начальн", "расчет средней цены", "обоснование цены")):
        return "NMCK"
    if any(marker in sample for marker in ("описание объекта закупки", "техническое задание", "технические характеристик", "характеристики товара")):
        return "TECHNICAL_SPEC"
    if "спецификац" in sample and any(marker in sample for marker in ("количество", "единица измерения", "наименование товара")):
        return "SPECIFICATION_TABLE"
    if any(marker in sample for marker in ("проект контракта", "поставщик обязуется", "заказчик обязуется", "порядок оплаты")):
        return "CONTRACT_DRAFT"
    if any(marker in sample for marker in ("извещение", "purchaseobject", "номер закупки")):
        return "NOTICE"
    if any(marker in sample for marker in ("инструкция", "заявк")):
        return "SUPPORTING"
    return "OTHER"


def detect_procurement_richness(document: Any) -> bool:
    text = str(getattr(document, "text", "") or "")
    return bool(_STANDARD.search(text) or _QUANTITY.search(text) or _CHARACTERISTIC.search(text) or _DELIVERY.search(text) or _WARRANTY.search(text))


def _fact(document: Any, role: str, row: int, kind: str, value: str, excerpt: str, *, unit: str | None = None, strategy: str = "generic_text_v1") -> ProcurementSourceFact:
    source = str(getattr(document, "display_name", ""))
    file_id = str(getattr(document, "file_id", ""))
    clean = " ".join(excerpt.split())
    normalized = re.sub(r"\W+", " ", value.lower().replace("ё", "е")).strip()
    digest = hashlib.sha256(f"{file_id}|{row}|{kind}|{value}".encode()).hexdigest()[:16]
    return ProcurementSourceFact(f"source_fact::{digest}", kind, normalized, value.strip(), unit, clean, source, file_id, role, f"line:{row}", clean[:500], "high", strategy, row)


def _table_item(document: Any, role: str, row: int, line: str) -> ProcurementSourceFact | None:
    cells = [" ".join(cell.split()) for cell in line.split("\t") if cell.strip()]
    if len(cells) < 3 or not re.fullmatch(r"\d{1,3}", cells[0]):
        return None
    name = next((cell for cell in cells[1:] if len(cell) > 3 and not _UNIT.fullmatch(cell) and not re.fullmatch(r"\d+(?:[.,]\d+)?", cell)), None)
    if not name or any(marker in name.lower() for marker in ("наименование", "характеристик", "значение")):
        return None
    return _fact(document, role, row, "PRODUCT_ITEM", name, line, strategy="generic_table_v1")


def _table_quantity(document: Any, role: str, row: int, line: str) -> ProcurementSourceFact | None:
    cells = [" ".join(cell.split()) for cell in line.split("\t") if cell.strip()]
    if len(cells) < 4 or not re.fullmatch(r"\d{1,3}", cells[0]):
        return None
    for index, cell in enumerate(cells[2:], start=2):
        if not re.fullmatch(r"\d+(?:[.,]\d+)?", cell):
            continue
        if index + 1 < len(cells) and _UNIT.fullmatch(cells[index + 1]):
            return _fact(document, role, row, "QUANTITY", cell, line, unit=cells[index + 1], strategy="generic_table_v1")
    return None


def extract_goods_source_facts(documents: list[Any]) -> list[ProcurementSourceFact]:
    """Extract bounded facts. Non-empty text is the sole eligibility condition."""
    facts: list[ProcurementSourceFact] = []
    seen: set[tuple[str, str, str, str]] = set()
    for document in documents:
        text = str(getattr(document, "text", "") or "")
        if not text:
            continue
        role = semantic_procurement_role(document)
        for row, raw_line in enumerate(text.replace("\f", "\n").splitlines(), start=1):
            line = " ".join(raw_line.split())
            if len(line) < 4:
                continue
            candidates: list[ProcurementSourceFact] = []
            item = _table_item(document, role, row, raw_line)
            if item:
                candidates.append(item)
            table_quantity = _table_quantity(document, role, row, raw_line)
            if table_quantity:
                candidates.append(table_quantity)
            for match in _PRODUCT.finditer(line):
                candidates.append(_fact(document, role, row, "PRODUCT_ITEM", match.group(1).strip(" .;"), line))
            for match in _QUANTITY.finditer(line):
                candidates.append(_fact(document, role, row, "QUANTITY", match.group(1), line, unit=match.group(2)))
            for match in _CHARACTERISTIC.finditer(line):
                candidates.append(_fact(document, role, row, "PRODUCT_CHARACTERISTIC", f"{match.group(1)} {match.group(2)}", line))
            for match in _STANDARD.finditer(line):
                candidates.append(_fact(document, role, row, "STANDARD", match.group(0), line))
            for pattern, kind in ((_DELIVERY, "DELIVERY_DEADLINE"), (_PLACE, "DELIVERY_PLACE"), (_WARRANTY, "WARRANTY")):
                for match in pattern.finditer(line):
                    candidates.append(_fact(document, role, row, kind, match.group(0), line))
            lowered = line.lower()
            if any(word in lowered for word in ("сертификат", "декларац", "паспорт качества")):
                candidates.append(_fact(document, role, row, "CERTIFICATE", line, line))
            if "безопасност" in lowered and any(word in lowered for word in ("соответств", "должен", "должна", "обеспеч")):
                candidates.append(_fact(document, role, row, "SAFETY", line, line))
            if "эквивалент" in lowered:
                candidates.append(_fact(document, role, row, "EQUIVALENT_RULE", line, line))
            for candidate in candidates:
                key = (candidate.file_id, candidate.fact_type, candidate.normalized_key, candidate.locator)
                if key not in seen:
                    seen.add(key)
                    facts.append(candidate)
    return facts


def build_goods_requirements_from_source_facts(facts: list[ProcurementSourceFact]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fact in facts:
        titles = {
            "PRODUCT_ITEM": fact.value,
            "QUANTITY": f"Количество: {fact.value} {fact.unit or ''}".strip(),
            "PRODUCT_CHARACTERISTIC": fact.value,
            "STANDARD": fact.value,
            "DELIVERY_DEADLINE": "Срок поставки",
            "DELIVERY_PLACE": "Место поставки",
            "WARRANTY": "Гарантийный срок",
            "CERTIFICATE": "Документы качества",
            "SAFETY": "Требования безопасности",
            "EQUIVALENT_RULE": "Условие эквивалентности",
        }
        title = titles.get(fact.fact_type, fact.value)
        rows.append({
            "title": title, "detail": fact.text, "source": fact.source_document,
            "source_document": fact.source_document, "type": fact.fact_type.lower(), "priority": "high",
            "source_fact_id": fact.fact_id, "locator": fact.locator, "excerpt": fact.excerpt,
            "evidence_candidate": {"evidence_id": fact.fact_id, "file_id": fact.file_id, "source_document": fact.source_document, "locator": fact.locator, "text": fact.excerpt},
        })
    return rows

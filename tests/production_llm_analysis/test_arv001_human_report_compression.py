from __future__ import annotations

from scripts.arv001.compress_human_report import compress_html, validate_compressed_presentation


def _row(text: str, evidence_id: str, source: str = "Проект контракта") -> dict:
    return {"text": text, "source": source, "evidence_id": evidence_id, "evidence_ids": [evidence_id]}


def _analysis() -> dict:
    return {
        "technical": {
            "standards": [],
            "specific_clauses": [
                _row("1 Топливо дизельное Сорт/класс топлива Не ниже 3 Согласно КТРУ 140 Тонна", "EV-T1", "Техническое задание"),
                _row("Экологический класс Не ниже К 5 Согласно КТРУ", "EV-T2", "Техническое задание"),
            ],
        },
        "contract": {
            "payment": [
                _row("Аванс не предусмотрен.", "EV-P1"),
                _row("Расчеты производятся не позднее 7 (семи) рабочих дней со дня подписания Заказчиком документа о приемке в ЕИС.", "EV-P2"),
                _row("размер этого обеспечения подлежит уменьшению в порядке статьи 96 ФЗ № 44.", "EV-P-NOISE"),
            ],
            "security": [
                _row("Размер обеспечения исполнения Контракта составляет _______ руб.", "EV-S1"),
                _row("Исполнение Контракта может обеспечиваться предоставлением независимой гарантии, соответствующей требованиям ст.", "EV-S2"),
                _row("45 ФЗ № 44, или внесением денежных средств на указанный Заказчиком счет.", "EV-S3"),
                _row("Срок действия независимой гарантии должен превышать срок обязательств не менее чем на один месяц.", "EV-S4"),
                _row("Денежные средства возвращаются в течение 15 (пятнадцати) дней с даты исполнения обязательств.", "EV-S5"),
            ],
            "acceptance": [
                _row("Поставщик в течение 4 (четырех) рабочих дней с даты передачи Товара размещает документ о приемке в ЕИС.", "EV-A1"),
                _row("В срок не позднее 20 (двадцати) рабочих дней после поступления документа о приемке Заказчик принимает решение.", "EV-A2"),
                _row("При несоответствиях Заказчик направляет мотивированный отказ с перечнем выявленных недостатков и сроков устранения.", "EV-A3"),
            ],
            "liability": [_row("Пеня устанавливается в размере одной трехсотой ключевой ставки за каждый день просрочки.", "EV-L1")],
            "liability_cap": [_row("Общая сумма начисленных штрафов Поставщику не может превышать цену Контракта.", "EV-C1")],
            "termination": [
                _row("Расторжение Контракта допускается по соглашению Сторон, по решению суда, в случае одностороннего отказа.", "EV-R1"),
                _row("РАСТОРЖЕНИЯ КОНТРАКТА", "EV-R-NOISE"),
            ],
        },
        "application_requirements": [
            _row("ж) выписка из единого государственного реестра юридических лиц", "EV-Q1", "Требования к составу заявки"),
            _row("н) документы по дополнительным требованиям статьи 31: не установлены", "EV-Q2", "Требования к составу заявки"),
            _row('к) декларация организации инвалидов, предусмотренной HYPERLINK "http://example.test" \\l "dst2205" частью 2 статьи 29', "EV-Q3", "Требования к составу заявки"),
            _row("м) решение об одобрении крупной сделки, если это является крупной сделкой", "EV-Q4", "Требования к составу заявки"),
            _row("в) документы, подтверждающие соответствие товара требованиям законодательства", "EV-Q5", "Требования к составу заявки"),
            _row("Информация и документы, подтверждающие страну происхождения товара:", "EV-Q6", "Требования к составу заявки"),
            _row("При отсутствии документов заявка приравнивается к заявке с предложением товара иностранного государства", "EV-Q7", "Требования к составу заявки"),
        ],
    }


def _contract() -> dict:
    analysis = _analysis()
    facts = []
    for row in analysis["technical"]["specific_clauses"]:
        facts.append({"label": "Техническое требование", "text": row["text"], "evidence_ids": row["evidence_ids"]})
    for rows in analysis["contract"].values():
        for row in rows:
            facts.append({"label": "Условие контракта", "text": row["text"], "evidence_ids": row["evidence_ids"]})
    for row in analysis["application_requirements"]:
        facts.append({"label": "Требование к заявке", "text": row["text"], "evidence_ids": row["evidence_ids"]})
    return {
        "decision": {"text": "HOLD — сначала подтвердить срок подачи", "evidence_ids": ["EV-T1", "EV-P1", "EV-S1"]},
        "next_action": {"text": "Подтвердить срок, размер обеспечения и экономику участия.", "evidence_ids": ["EV-DEADLINE", "EV-S1", "EV-ECON"]},
        "facts": facts,
        "uncertainty": [
            {"code": "deadline_not_confirmed", "text": "Текущий статус срока не подтверждён.", "evidence_ids": ["EV-DEADLINE"]},
            {"code": "performance_security_amount_unresolved", "text": "Размер обеспечения не заполнен.", "evidence_ids": ["EV-S1"]},
            {"code": "commercial_economics_not_calculated", "text": "Экономика участия не рассчитана.", "evidence_ids": ["EV-ECON"]},
        ],
        "caveats": [{"text": "Выводы относятся к зафиксированному комплекту документов.", "evidence_ids": ["EV-DEADLINE"]}],
    }


def _html() -> str:
    return """<!doctype html><html><body><main>
<section><h1>Анализ закупки № 0388100001826000047</h1></section>
<section><h2>Закупка 0388100001826000047.</h2><p>Заказчик: ЧУКОТСКОЕ УГМС</p><p>Место поставки: г. Архангельск</p></section>
<section class="decision"><h2>old</h2></section>
<section><h2>Состав и объём закупки</h2><table><tr><td>Топливо</td><td>—</td></tr></table><p>Подробные требования приведены ниже в разделе «Технические требования».</p></section>
<section><h2>Технические требования</h2><p>mixed</p></section>
<section><h2>Требования к заявке и участнику</h2><p>mixed</p></section>
<section><h2>Условия контракта</h2><p>mixed</p></section>
<section><h2>Ограничения текущего автоматического извлечения</h2><p>generic</p></section>
<section><h2>Контроль перед коммерческим решением</h2><p>Проверить конкретный срок и порядок оплаты по проекту контракта.</p></section>
<section><h2>Источники</h2><p>Извещение</p></section>
</main></body></html>"""


def test_compression_keeps_raw_evidence_collapsed_and_human_view_compact() -> None:
    rendered = compress_html(_html(), _analysis(), _contract())
    validate_compressed_presentation(rendered)

    assert 'data-presentation="compressed-v1"' in rendered
    assert '<details class="audit-evidence">' in rendered
    visible = rendered.split('<details class="audit-evidence">', 1)[0]
    assert "Evidence ID:" not in visible
    assert "HYPERLINK" not in visible
    assert "Аванс не предусмотрен" in visible
    assert "7 рабочих дней" in visible
    assert "Размер обеспечения исполнения" in visible
    assert "сорт/класс топлива ≥ 3" in rendered
    assert "экологический класс ≥ К5" in rendered
    assert "Ограничения текущего автоматического извлечения" not in rendered
    assert "Проверить конкретный срок и порядок оплаты" not in rendered
    assert "<h2>Источники</h2>" not in rendered

    # Exact raw evidence remains available for fail-closed audit validation.
    assert 'HYPERLINK &quot;http://example.test&quot; \\l &quot;dst2205&quot;' in rendered
    assert "EV-P-NOISE" in rendered
    assert "РАСТОРЖЕНИЯ КОНТРАКТА" in rendered


def test_compression_separates_application_and_contract_concerns() -> None:
    rendered = compress_html(_html(), _analysis(), _contract())
    application = rendered.split("<h2>Требования к заявке и участнику</h2>", 1)[1].split("</section>", 1)[0]
    contract = rendered.split("<h2>Условия контракта</h2>", 1)[1].split("</section>", 1)[0]

    assert "Регистрационные сведения" in application
    assert "не установлены" in application
    assert "Документы на товар" in application
    assert "Страна происхождения / нацрежим" in application
    assert "Специальные статусы — только если применимо" in application
    assert "HYPERLINK" not in application
    assert "Топливо дизельное" not in application

    assert "Аванс: не предусмотрен" in contract
    assert "Оплата: не позднее 7 рабочих дней" in contract
    assert "размер этого обеспечения подлежит уменьшению" not in contract
    assert "Пеня за просрочку поставщика" in contract
    assert "Совокупная сумма начисленных поставщику штрафов" in contract

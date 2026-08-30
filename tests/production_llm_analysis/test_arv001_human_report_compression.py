from __future__ import annotations

from scripts.arv001.compress_human_report import compress_html, validate_compressed_presentation


def _row(text: str, evidence_id: str, source: str = "Проект контракта") -> dict:
    return {
        "text": text,
        "source": source,
        "evidence_id": evidence_id,
        "evidence_ids": [evidence_id],
    }


def _analysis() -> dict:
    return {
        "technical": {
            "standards": [],
            "specific_clauses": [
                _row(
                    "1 Топливо дизельное Сорт/класс топлива Не ниже 3 Согласно КТРУ 140 Тонна",
                    "EV-TECH-1",
                    "Техническое задание",
                ),
                _row(
                    "Экологический класс Не ниже К 5 Согласно КТРУ",
                    "EV-TECH-2",
                    "Техническое задание",
                ),
            ],
        },
        "contract": {
            "payment": [
                _row("Аванс не предусмотрен.", "EV-PAY-1"),
                _row(
                    "Расчеты производятся не позднее 7 (семи) рабочих дней со дня подписания Заказчиком документа о приемке в ЕИС.",
                    "EV-PAY-2",
                ),
                _row(
                    "размер этого обеспечения подлежит уменьшению в порядке статьи 96 ФЗ № 44.",
                    "EV-PAY-NOISE",
                ),
            ],
            "security": [
                _row(
                    "Размер обеспечения исполнения Контракта составляет _______ руб.",
                    "EV-SEC-1",
                ),
                _row(
                    "Исполнение Контракта может обеспечиваться предоставлением независимой гарантии, соответствующей требованиям ст.",
                    "EV-SEC-2",
                ),
                _row(
                    "45 ФЗ № 44, или внесением денежных средств на указанный Заказчиком счет.",
                    "EV-SEC-3",
                ),
                _row(
                    "Срок действия независимой гарантии должен превышать срок обязательств не менее чем на один месяц.",
                    "EV-SEC-4",
                ),
                _row(
                    "Денежные средства возвращаются в течение 15 (пятнадцати) дней с даты исполнения обязательств.",
                    "EV-SEC-5",
                ),
            ],
            "acceptance": [
                _row(
                    "Поставщик в течение 4 (четырех) рабочих дней с даты передачи Товара размещает документ о приемке в ЕИС.",
                    "EV-ACC-1",
                ),
                _row(
                    "В срок не позднее 20 (двадцати) рабочих дней после поступления документа о приемке Заказчик принимает решение.",
                    "EV-ACC-2",
                ),
                _row(
                    "При несоответствиях Заказчик направляет мотивированный отказ с перечнем выявленных недостатков и сроков устранения.",
                    "EV-ACC-3",
                ),
            ],
            "liability": [
                _row(
                    "Пеня устанавливается в размере одной трехсотой ключевой ставки за каждый день просрочки.",
                    "EV-LIA-1",
                )
            ],
            "liability_cap": [
                _row(
                    "Общая сумма начисленных штрафов Поставщику не может превышать цену Контракта.",
                    "EV-CAP-1",
                )
            ],
            "termination": [
                _row(
                    "Расторжение Контракта допускается по соглашению Сторон, по решению суда, в случае одностороннего отказа.",
                    "EV-TERM-1",
                ),
                _row("РАСТОРЖЕНИЯ КОНТРАКТА", "EV-TERM-NOISE"),
            ],
        },
        "application_requirements": [
            _row(
                "ТРЕБОВАНИЯ К СОДЕРЖАНИЮ, СОСТАВУ ЗАЯВКИ НА УЧАСТИЕ",
                "EV-APP-HEAD",
                "Требования к составу заявки",
            ),
            _row(
                "ж) выписка из единого государственного реестра юридических лиц",
                "EV-APP-1",
                "Требования к составу заявки",
            ),
            _row(
                "н) документы по дополнительным требованиям статьи 31: не установлены",
                "EV-APP-2",
                "Требования к составу заявки",
            ),
            _row(
                'к) декларация организации инвалидов, предусмотренной HYPERLINK "http://example.test" \\l "dst2205" частью 2 статьи 29',
                "EV-APP-3",
                "Требования к составу заявки",
            ),
            _row(
                "м) решение об одобрении крупной сделки, если это является крупной сделкой",
                "EV-APP-4",
                "Требования к составу заявки",
            ),
            _row(
                "в) документы, подтверждающие соответствие товара требованиям законодательства",
                "EV-APP-5",
                "Требования к составу заявки",
            ),
            _row(
                "Информация и документы, подтверждающие страну происхождения товара:",
                "EV-APP-6",
                "Требования к составу заявки",
            ),
            _row(
                "При отсутствии документов заявка приравнивается к заявке с предложением товара иностранного государства",
                "EV-APP-7",
                "Требования к составу заявки",
            ),
        ],
    }


def _contract() -> dict:
    all_facts = []
    analysis = _analysis()
    for group in analysis["technical"]["specific_clauses"]:
        all_facts.append({"label": "Техническое требование", "text": group["text"], "evidence_ids": group["evidence_ids"]})
    for key, rows in analysis["contract"].items():
        if isinstance(rows, list):
            for row in rows:
                all_facts.append({"label": key, "text": row["text"], "evidence_ids": row["evidence_ids"]})
    for row in analysis["application_requirements"]:
        all_facts.append({"label": "Требование к заявке / участнику", "text": row["text"], "evidence_ids": row["evidence_ids"]})
    return {
        "decision": {
            "text": "HOLD — сначала подтвердить срок подачи",
            "evidence_ids": ["EV-TECH-1", "EV-PAY-1", "EV-SEC-1"],
        },
        "next_action": {
            "text": "Подтвердить срок, размер обеспечения и экономику участия.",
            "evidence_ids": ["EV-DEADLINE", "EV-SEC-1", "EV-ECON"],
        },
        "facts": all_facts,
        "uncertainty": [
            {"code": "deadline_not_confirmed", "text": "Текущий статус срока не подтверждён.", "evidence_ids": ["EV-DEADLINE"]},
            {"code": "performance_security_amount_unresolved", "text": "Размер обеспечения не заполнен.", "evidence_ids": ["EV-SEC-1"]},
            {"code": "commercial_economics_not_calculated", "text": "Экономика участия не рассчитана.", "evidence_ids": ["EV-ECON"]},
        ],
        "caveats": [
            {"text": "Выводы относятся к зафиксированному комплекту документов.", "evidence_ids": ["EV-DEADLINE"]}
        ],
    }


def _html() -> str:
    return """<!doctype html><html><body><main>
<section><h1>Анализ закупки № 0388100001826000047</h1><details><summary>Документы комплекта (6)</summary></details></section>
<section><h2>Закупка 0388100001826000047.</h2><p>Заказчик: ЧУКОТСКОЕ УГМС</p><p>Место поставки: г. Архангельск</p></section>
<section class="decision"><h2>old</h2></section>
<section><h2>Состав и объём закупки</h2><table><tr><td>Топливо</td><td>—</td></tr></table><p>Подробные требования приведены ниже в разделе «Технические требования».</p></section>
<section><h2>Технические требования</h2><p>mixed raw data</p></section>
<section><h2>Требования к заявке и участнику</h2><p>mixed raw data</p></section>
<section><h2>Условия контракта</h2><p>duplicated raw data</p></section>
<section><h2>Ограничения текущего автоматического извлечения</h2><p>generic limitations</p></section>
<section><h2>Контроль перед коммерческим решением</h2><li>Проверить конкретный срок и порядок оплаты по проекту контракта.</li></section>
<section><h2>Источники</h2><ul><li>Извещение</li></ul></section>
</main></body></html>"""


def test_compressed_report_prioritizes_human_summary_and_collapses_raw_evidence() -> None:
    rendered = compress_html(_html(), _analysis(), _contract())
    validate_compressed_presentation(rendered)

    assert 'data-presentation="compressed-v1"' in rendered
    assert '<details class="audit-evidence">' in rendered
    visible_decision = rendered.split('<details class="audit-evidence">', 1)[0]
    assert "Evidence ID:" not in visible_decision
    assert "HYPERLINK" not in visible_decision
    assert "Аванс не предусмотрен" in visible_decision
    assert "7 рабочих дней" in visible_decision
    assert "Размер обеспечения исполнения" in visible_decision

    assert "сорт/класс топлива ≥ 3" in rendered
    assert "экологический класс ≥ К5" in rendered
    assert "Технические требования" in rendered
    assert "Требования к заявке и участнику" in rendered
    assert "Условия контракта" in rendered
    assert "Что осталось проверить" in rendered

    assert "Проверить конкретный срок и порядок оплаты" not in rendered
    assert "Ограничения текущего автоматического извлечения" not in rendered
    assert "<h2>Источники</h2>" not in rendered

    # Raw source evidence remains byte-for-text available only inside the collapsed audit appendix.
    assert 'HYPERLINK &quot;http://example.test&quot; \\l &quot;dst2205&quot;' in rendered
    assert "EV-PAY-NOISE" in rendered
    assert "РАСТОРЖЕНИЯ КОНТРАКТА" in rendered


def test_application_summary_separates_conditional_statuses_from_core_requirements() -> None:
    rendered = compress_html(_html(), _analysis(), _contract())
    section = rendered.split("<h2>Требования к заявке и участнику</h2>", 1)[1].split("</section>", 1)[0]

    assert "Регистрационные сведения" in section
    assert "Дополнительные требования" not in section  # label is intentionally humanized
    assert "не установлены" in section
    assert "Документы на товар" in section
    assert "Страна происхождения / нацрежим" in section
    assert "Специальные статусы — только если применимо" in section
    assert "HYPERLINK" not in section
    assert "Топливо дизельное" not in section


def test_contract_summary_drops_overlapping_payment_noise_but_keeps_audit_fact() -> None:
    rendered = compress_html(_html(), _analysis(), _contract())
    section = rendered.split("<h2>Условия контракта</h2>", 1)[1].split("</section>", 1)[0]

    assert "Аванс: не предусмотрен" in section
    assert "Оплата: не позднее 7 рабочих дней" in section
    assert "размер этого обеспечения подлежит уменьшению" not in section
    assert "Пеня за просрочку поставщика" in section
    assert "Совокупная сумма начисленных поставщику штрафов" in section
    assert "EV-PAY-NOISE" in rendered

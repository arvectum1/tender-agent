import json
from types import SimpleNamespace


def test_parse_public_notice_attachments_extracts_real_documents_and_skips_sign_links():
    from src.modules.tender_operator_agent_demo import procurement_intake_service as service

    documents_html = """
    <div class="attachmentsTabDocs">
      <div class="attachment row ">
        <div class="col clipText">
          <a data-modalup href="/epz/order/notice/signview/ep/listModal.html?reestrNumber=0373200000000000001&uid=sign-only">
            sign
          </a>
          <img alt="Adobe Acrobat Document" src="/epz/static/img/icons/type/pdf.svg"/>
          <span class="section__value">
            <a href="/44fz/filestore/public/1.0/download/priz/file.html?uid=UID001" title="Техническое задание.pdf">
              Техническое задание
            </a>
          </span>
        </div>
      </div>
      <div class="attachment row ">
        <div class="col clipText">
          <img alt="Microsoft Excel Document" src="/epz/static/img/icons/type/xlsx.svg"/>
          <span class="section__value">
            <a href="https://zakupki.gov.ru/44fz/filestore/public/1.0/download/priz/file.html?uid=UID002" title="Расчет НМЦК.xlsx">
              Расчет НМЦК
            </a>
          </span>
        </div>
      </div>
    </div>
    """

    attachments = service._parse_public_notice_attachments(
        documents_html,
        page_url="https://zakupki.gov.ru/epz/order/notice/ea44/view/documents.html?regNumber=0373200000000000001",
    )

    assert [item.name for item in attachments] == ["Техническое задание.pdf", "Расчет НМЦК.xlsx"]
    assert attachments[0].url == "https://zakupki.gov.ru/44fz/filestore/public/1.0/download/priz/file.html?uid=UID001"
    assert attachments[1].attachment_id == "UID002"


def test_public_notice_attachment_fetch_uses_source_controlled_provider(monkeypatch):
    from src.modules.tender_operator_agent_demo import procurement_intake_service as service

    captured = {}

    class FakeProvider:
        def __init__(self, *, bypass_proxy):
            captured["bypass_proxy"] = bypass_proxy

        def fetch_detail(self, *, card_url):
            captured["card_url"] = card_url
            return SimpleNamespace(
                document_links=[
                    SimpleNamespace(
                        file_name="Описание объекта закупки.docx",
                        title=None,
                        url="https://zakupki.gov.ru/44fz/filestore/public/1.0/download/priz/file.html?uid=UID001",
                        raw={"uid": "UID001"},
                    )
                ]
            )

    monkeypatch.setattr(service, "Public44FzSearchProvider", FakeProvider)

    attachments = service._fetch_public_notice_attachments(
        "https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0373200000000000001"
    )

    assert captured == {
        "bypass_proxy": True,
        "card_url": "https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0373200000000000001",
    }
    assert attachments[0].name == "Описание объекта закупки.docx"
    assert attachments[0].attachment_id == "UID001"


def test_handoff_endpoint_requires_reestr_number(client, monkeypatch, tmp_path):
    from src.modules.tender_operator_agent_demo import procurement_intake_service as service
    from src.modules.tender_operator_agent_demo.settings import clear_zakupki_soap_settings_cache

    runs_root = tmp_path / "tender_operator_demo_runs"
    monkeypatch.setenv("AI_CORP_TENDER_OPERATOR_DEMO_RUNS_DIR", str(runs_root))
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_ENABLED", "1")
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_TOKEN", "test-token-value-not-real")
    clear_zakupki_soap_settings_cache()

    response = client.post(
        "/api/demo/tender-agent/runs/from-search-result",
        json={
            "source": "public_44fz",
            "reestr_number": "",
            "download_archive": False,
            "analyze_after_download": False,
        },
    )
    assert response.status_code == 400
    assert "reestr_number" in response.json()["detail"].lower()


def test_handoff_endpoint_calls_getdocs_ip(client, monkeypatch, tmp_path):
    from src.modules.tender_operator_agent_demo import procurement_intake_service as service
    from src.modules.tender_operator_agent_demo.procurement_schemas import DocsArchiveResult, DownloadedAttachment
    from src.modules.tender_operator_agent_demo.settings import clear_zakupki_soap_settings_cache

    runs_root = tmp_path / "tender_operator_demo_runs"
    monkeypatch.setenv("AI_CORP_TENDER_OPERATOR_DEMO_RUNS_DIR", str(runs_root))
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_ENABLED", "1")
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_TOKEN", "test-token-value-not-real")
    clear_zakupki_soap_settings_cache()

    class FakeClient:
        def __init__(self, _settings):
            pass

        def get_docs_by_reestr_number(self, _reestr_number, subsystem_type="PRIZ"):
            return DocsArchiveResult(
                request_id="req-handoff-001",
                ref_id="ref-handoff-001",
                archive_url="https://int44.zakupki.gov.ru/archive/demo.zip",
                status="completed",
                warnings=[],
                safe_diagnostic={"archive_url_present": True},
            )

        def download_archive(self, _archive_url, target_dir):
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "documentation-archive.zip").write_bytes(b"PK\x03\x04demo")
            return DownloadedAttachment(
                file_name="demo.zip",
                stored_name="documentation-archive.zip",
                size_bytes=10,
                content_type="application/zip",
                source_url_host="int44.zakupki.gov.ru",
                source_url_path="/archive/demo.zip",
            )

    monkeypatch.setattr(service, "ZakupkiSoapClient", FakeClient)
    monkeypatch.setattr(
        service,
        "_extract_safe_archive_into_run",
        lambda run_id, _path: (
            [
                service.build_demo_file_descriptor(
                    file_id="FILE-01",
                    original_name="notice.txt",
                    stored_name="01-notice.txt",
                    size_bytes=10,
                    content_type="text/plain",
                    source="eis_getdocs_archive",
                )
            ],
            [
                service.ProcurementAttachmentManifestItem(
                    name="notice.txt",
                    stored_name="01-notice.txt",
                    extension=".txt",
                    status="saved",
                    note="ok",
                )
            ],
            1,
        ),
    )

    response = client.post(
        "/api/demo/tender-agent/runs/from-search-result",
        json={
            "source": "public_44fz",
            "reestr_number": "0888200000224000038",
            "title": "Поставка оборудования",
            "customer_name": "ООО Тестовый заказчик",
            "source_url": "https://zakupki.gov.ru/epz/order/notice/ea44/view.html?regNumber=0888200000224000038",
            "download_archive": True,
            "analyze_after_download": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"]
    assert payload["run_id"]
    assert payload["archive_url_present"] is True
    assert "ticket" not in json.dumps(payload, ensure_ascii=False)

    metadata = json.loads((runs_root / payload["run_id"] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["tender_title"] == "Поставка оборудования"
    assert metadata["customer_name"] == "ООО Тестовый заказчик"
    assert metadata["procurement_url"] == "https://zakupki.gov.ru/epz/order/notice/ea44/view.html?regNumber=0888200000224000038"
    clear_zakupki_soap_settings_cache()


def test_handoff_source_url_sanitized(client, monkeypatch, tmp_path):
    from src.modules.tender_operator_agent_demo import procurement_intake_service as service
    from src.modules.tender_operator_agent_demo.procurement_schemas import DocsArchiveResult, DownloadedAttachment
    from src.modules.tender_operator_agent_demo.settings import clear_zakupki_soap_settings_cache

    runs_root = tmp_path / "tender_operator_demo_runs"
    monkeypatch.setenv("AI_CORP_TENDER_OPERATOR_DEMO_RUNS_DIR", str(runs_root))
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_ENABLED", "1")
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_TOKEN", "test-token-value-not-real")
    clear_zakupki_soap_settings_cache()

    class FakeClient:
        def __init__(self, _settings):
            pass

        def get_docs_by_reestr_number(self, _reestr_number, subsystem_type="PRIZ"):
            return DocsArchiveResult(
                request_id="req-002",
                ref_id=None,
                archive_url=None,
                status="no_archive_url",
                warnings=[],
                safe_diagnostic={"archive_url_present": False},
            )

    monkeypatch.setattr(service, "ZakupkiSoapClient", FakeClient)

    response = client.post(
        "/api/demo/tender-agent/runs/from-search-result",
        json={
            "source": "public_44fz",
            "reestr_number": "0888200000224000038",
            "title": "Тест",
            "source_url": "https://zakupki.gov.ru/",
            "download_archive": False,
            "analyze_after_download": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in ("completed", "failed", "archive_not_ready", "completed_with_warnings", "archive_downloaded", "manual_upload_required", "docs_required")
    clear_zakupki_soap_settings_cache()


def test_handoff_223fz_works_without_getdocs_token(client, monkeypatch, tmp_path):
    from src.modules.tender_operator_agent_demo import procurement_intake_service as service
    from src.modules.tender_operator_agent_demo.settings import clear_zakupki_soap_settings_cache

    runs_root = tmp_path / "tender_operator_demo_runs"
    monkeypatch.setenv("AI_CORP_TENDER_OPERATOR_DEMO_RUNS_DIR", str(runs_root))
    monkeypatch.delenv("ZAKUPKI_GOV_RU_SOAP_ENABLED", raising=False)
    monkeypatch.delenv("ZAKUPKI_GOV_RU_SOAP_TOKEN", raising=False)
    clear_zakupki_soap_settings_cache()

    monkeypatch.setattr(
        service,
        "_extract_public_page_context",
        lambda _url: {
            "title": "Оказание услуг по обучению",
            "customer_name": "АО Тестовый заказчик",
            "publication_date": "02.07.2026",
            "deadline": "10.07.2026 10:00",
            "initial_price": 250000.0,
            "currency": "RUB",
        },
    )

    response = client.post(
        "/api/demo/tender-agent/runs/from-search-result",
        json={
            "source": "public_eis_html_223fz",
            "law": "223fz",
            "reestr_number": "32616173212",
            "source_url": "https://zakupki.gov.ru/223/purchase/public/purchase/info/common-info.html?regNumber=32616173212",
            "download_archive": True,
            "analyze_after_download": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    metadata = json.loads((runs_root / payload["run_id"] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["tender_title"] == "Оказание услуг по обучению"
    assert metadata["customer_name"] == "АО Тестовый заказчик"
    assert metadata["tender_category"] == "223-ФЗ"
    assert metadata["procurement_source"] == "public_eis_html_223fz"
    clear_zakupki_soap_settings_cache()


def test_handoff_can_enrich_context_from_public_source_url(client, monkeypatch, tmp_path):
    from src.modules.tender_operator_agent_demo import procurement_intake_service as service
    from src.modules.tender_operator_agent_demo.procurement_schemas import DocsArchiveResult
    from src.modules.tender_operator_agent_demo.settings import clear_zakupki_soap_settings_cache

    runs_root = tmp_path / "tender_operator_demo_runs"
    monkeypatch.setenv("AI_CORP_TENDER_OPERATOR_DEMO_RUNS_DIR", str(runs_root))
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_ENABLED", "1")
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_TOKEN", "test-token-value-not-real")
    clear_zakupki_soap_settings_cache()

    class FakeClient:
        def __init__(self, _settings):
            pass

        def get_docs_by_reestr_number(self, _reestr_number, subsystem_type="PRIZ"):
            return DocsArchiveResult(
                request_id="req-ctx-001",
                ref_id="ref-ctx-001",
                archive_url=None,
                status="no_archive_url",
                warnings=[],
                safe_diagnostic={"archive_url_present": False},
            )

    monkeypatch.setattr(service, "ZakupkiSoapClient", FakeClient)
    monkeypatch.setattr(
        service,
        "_extract_public_page_context",
        lambda _url: {
            "title": "Поставка картриджей",
            "customer_name": "ГКУ ЧАО МФЦ",
            "publication_date": "18.11.2024",
            "deadline": "25.11.2024 09:00",
            "initial_price": 149716.65,
            "currency": "RUB",
        },
    )

    response = client.post(
        "/api/demo/tender-agent/runs/from-search-result",
        json={
            "source": "public_44fz",
            "reestr_number": "0888200000224000038",
            "source_url": "https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0888200000224000038",
            "download_archive": False,
            "analyze_after_download": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    metadata = json.loads((runs_root / payload["run_id"] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["tender_title"] == "Поставка картриджей"
    assert metadata["customer_name"] == "ГКУ ЧАО МФЦ"
    assert metadata["publication_date"] == "18.11.2024"
    assert metadata["deadline"] == "25.11.2024 09:00"
    assert metadata["procurement"]["initial_price"] == 149716.65
    assert metadata["procurement"]["currency"] == "RUB"
    clear_zakupki_soap_settings_cache()


def test_handoff_supplements_public_documents_when_getdocs_archive_contains_only_xml(client, monkeypatch, tmp_path):
    from src.modules.tender_operator_agent_demo import procurement_intake_service as service
    from src.modules.tender_operator_agent_demo.attachment_downloader import (
        AttachmentDownloadManifestItem,
        AttachmentDownloadResult,
    )
    from src.modules.tender_operator_agent_demo.procurement_schemas import DocsArchiveResult, DownloadedAttachment, ProcurementAttachment
    from src.modules.tender_operator_agent_demo.settings import clear_zakupki_soap_settings_cache

    runs_root = tmp_path / "tender_operator_demo_runs"
    monkeypatch.setenv("AI_CORP_TENDER_OPERATOR_DEMO_RUNS_DIR", str(runs_root))
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_ENABLED", "1")
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_TOKEN", "test-token-value-not-real")
    clear_zakupki_soap_settings_cache()

    class FakeClient:
        def __init__(self, _settings):
            pass

        def get_docs_by_reestr_number(self, _reestr_number, subsystem_type="PRIZ"):
            return DocsArchiveResult(
                request_id="req-docs-001",
                ref_id="ref-docs-001",
                archive_url="https://int.zakupki.gov.ru/archive/demo.zip",
                status="completed",
                warnings=[],
                safe_diagnostic={"archive_url_present": True},
            )

        def download_archive(self, _archive_url, target_dir):
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "documentation-archive.zip").write_bytes(b"PK\x03\x04demo")
            return DownloadedAttachment(
                file_name="demo.zip",
                stored_name="documentation-archive.zip",
                size_bytes=10,
                content_type="application/zip",
                source_url_host="int.zakupki.gov.ru",
                source_url_path="/archive/demo.zip",
            )

    monkeypatch.setattr(service, "ZakupkiSoapClient", FakeClient)
    monkeypatch.setattr(
        service,
        "_extract_safe_archive_into_run",
        lambda run_id, _path: (
            [
                service.build_demo_file_descriptor(
                    file_id="FILE-01",
                    original_name="epNotification.xml",
                    stored_name="extracted/01-epnotification.xml",
                    size_bytes=10,
                    content_type="application/xml",
                    source="eis_getdocs_archive",
                )
            ],
            [
                service.ProcurementAttachmentManifestItem(
                    name="epNotification.xml",
                    stored_name="extracted/01-epnotification.xml",
                    extension=".xml",
                    status="saved",
                    note="ok",
                )
            ],
            1,
        ),
    )
    monkeypatch.setattr(
        service,
        "_fetch_public_notice_attachments",
        lambda _url: [
            ProcurementAttachment(
                attachment_id="uid-tech-001",
                name="Приложение № 2 - Описание объекта закупки.docx",
                url="https://zakupki.gov.ru/44fz/filestore/public/1.0/download/priz/file.html?uid=uid-tech-001",
                extension=".docx",
                can_download=True,
                requires_manual_upload=False,
            ),
            ProcurementAttachment(
                attachment_id="uid-contract-001",
                name="Проект контракта.docx",
                url="https://zakupki.gov.ru/44fz/filestore/public/1.0/download/priz/file.html?uid=uid-contract-001",
                extension=".docx",
                can_download=True,
                requires_manual_upload=False,
            ),
        ],
    )

    def fake_download(attachments, *, target_dir, **_kwargs):
        target_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for index, attachment in enumerate(attachments, start=1):
            stored_name = f"{index:02d}-public-doc-{index}.docx"
            (target_dir / stored_name).write_bytes(f"payload-{index}".encode("utf-8"))
            saved.append(
                AttachmentDownloadManifestItem(
                    name=attachment.name,
                    stored_name=stored_name,
                    extension=".docx",
                    status="saved",
                    note="ok",
                    size_bytes=9,
                )
            )
        return AttachmentDownloadResult(saved=saved, skipped=[])

    monkeypatch.setattr(service, "download_procurement_attachments", fake_download)

    response = client.post(
        "/api/demo/tender-agent/runs/from-search-result",
        json={
            "source": "public_44fz",
            "reestr_number": "0122300006126000830",
            "source_url": "https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=0122300006126000830",
            "download_archive": True,
            "analyze_after_download": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    metadata = json.loads((runs_root / payload["run_id"] / "metadata.json").read_text(encoding="utf-8"))
    assert len(metadata["files"]) == 3
    assert any(item["role_hint"] == "technical_spec" for item in metadata["files"])
    assert any(item["role_hint"] == "contract_draft" for item in metadata["files"])
    assert metadata["downloaded_files_count"] == 3
    assert metadata["attachments_status"] == "downloaded"

    manifest = json.loads((runs_root / payload["run_id"] / "procurement" / "attachments_manifest.json").read_text(encoding="utf-8"))
    assert any(item["name"] == "Приложение № 2 - Описание объекта закупки.docx" for item in manifest)
    assert any(item["name"] == "Проект контракта.docx" for item in manifest)
    clear_zakupki_soap_settings_cache()


def test_handoff_supplements_documents_from_notice_xml_when_public_documents_are_empty(client, monkeypatch, tmp_path):
    from src.modules.tender_operator_agent_demo import procurement_intake_service as service
    from src.modules.tender_operator_agent_demo.attachment_downloader import (
        AttachmentDownloadManifestItem,
        AttachmentDownloadResult,
    )
    from src.modules.tender_operator_agent_demo.procurement_schemas import DocsArchiveResult, DownloadedAttachment
    from src.modules.tender_operator_agent_demo.settings import clear_zakupki_soap_settings_cache

    runs_root = tmp_path / "tender_operator_demo_runs"
    monkeypatch.setenv("AI_CORP_TENDER_OPERATOR_DEMO_RUNS_DIR", str(runs_root))
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_ENABLED", "1")
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_TOKEN", "test-token-value-not-real")
    clear_zakupki_soap_settings_cache()

    class FakeClient:
        def __init__(self, _settings):
            pass

        def get_docs_by_reestr_number(self, _reestr_number, subsystem_type="PRIZ"):
            return DocsArchiveResult(
                request_id="req-docs-xml-001",
                ref_id="ref-docs-xml-001",
                archive_url="https://int.zakupki.gov.ru/archive/demo.zip",
                status="completed",
                warnings=[],
                safe_diagnostic={"archive_url_present": True},
            )

        def download_archive(self, _archive_url, target_dir):
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "documentation-archive.zip").write_bytes(b"PK\x03\x04demo")
            return DownloadedAttachment(
                file_name="demo.zip",
                stored_name="documentation-archive.zip",
                size_bytes=10,
                content_type="application/zip",
                source_url_host="int.zakupki.gov.ru",
                source_url_path="/archive/demo.zip",
            )

    xml_notice = """<?xml version="1.0" encoding="UTF-8"?>
    <epNotification xmlns="http://zakupki.gov.ru/44fz/types/1">
      <attachmentsInfo>
        <attachmentInfo>
          <fileName>Описание объекта закупки.docx</fileName>
          <url>https://zakupki.gov.ru/44fz/filestore/public/1.0/download/priz/file.html?uid=uid-tech-xml</url>
        </attachmentInfo>
        <attachmentInfo>
          <fileName>Проект контракта.docx</fileName>
          <url>https://zakupki.gov.ru/44fz/filestore/public/1.0/download/priz/file.html?uid=uid-contract-xml</url>
        </attachmentInfo>
      </attachmentsInfo>
    </epNotification>
    """

    monkeypatch.setattr(service, "ZakupkiSoapClient", FakeClient)
    monkeypatch.setattr(
        service,
        "_extract_safe_archive_into_run",
        lambda run_id, _path: (
            [
                service.build_demo_file_descriptor(
                    file_id="FILE-01",
                    original_name="epNotificationEF2020.xml",
                    stored_name="extracted/01-epnotification.xml",
                    role_hint="notice",
                    size_bytes=len(xml_notice.encode("utf-8")),
                    content_type="application/xml",
                    source="eis_getdocs_archive",
                    source_type="getdocs_archive",
                    document_kind="eis_notice",
                )
            ],
            [
                service.ProcurementAttachmentManifestItem(
                    name="epNotificationEF2020.xml",
                    stored_name="extracted/01-epnotification.xml",
                    extension=".xml",
                    status="saved",
                    note="ok",
                    source_type="getdocs_archive",
                    document_kind="eis_notice",
                )
            ],
            1,
        ),
    )
    monkeypatch.setattr(service, "_fetch_public_notice_attachments", lambda _url: [])

    def fake_download(attachments, *, target_dir, **_kwargs):
        target_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for index, attachment in enumerate(attachments, start=1):
            stored_name = f"{index:02d}-notice-xml-{index}.docx"
            (target_dir / stored_name).write_bytes(f"payload-{index}".encode("utf-8"))
            saved.append(
                AttachmentDownloadManifestItem(
                    name=attachment.name,
                    stored_name=stored_name,
                    extension=".docx",
                    status="saved",
                    note="ok",
                    size_bytes=9,
                    source_url=attachment.url,
                    document_kind=attachment.document_kind,
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            )
        return AttachmentDownloadResult(saved=saved, skipped=[])

    monkeypatch.setattr(service, "download_procurement_attachments", fake_download)

    response = client.post(
        "/api/demo/tender-agent/runs/from-search-result",
        json={
            "source": "public_44fz",
            "reestr_number": "0122300006126000831",
            "source_url": "https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber=0122300006126000831",
            "download_archive": True,
            "analyze_after_download": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    run_dir = runs_root / payload["run_id"]
    (run_dir / "input" / "extracted").mkdir(parents=True, exist_ok=True)
    (run_dir / "input" / "extracted" / "01-epnotification.xml").write_text(xml_notice, encoding="utf-8")

    saved_count = service._supplement_run_with_notice_xml_attachments(payload["run_id"])
    assert saved_count == 2

    metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert len(metadata["files"]) == 3
    assert any(item["document_kind"] == "procurement_object_description" for item in metadata["files"])
    assert any(item["role_hint"] == "contract_draft" for item in metadata["files"])
    clear_zakupki_soap_settings_cache()


def test_existing_getdocs_intake_tests_still_pass(client, monkeypatch, tmp_path):
    from src.modules.tender_operator_agent_demo import procurement_intake_service as service
    from src.modules.tender_operator_agent_demo.procurement_schemas import DocsArchiveResult, DownloadedAttachment
    from src.modules.tender_operator_agent_demo.settings import clear_zakupki_soap_settings_cache

    runs_root = tmp_path / "tender_operator_demo_runs"
    monkeypatch.setenv("AI_CORP_TENDER_OPERATOR_DEMO_RUNS_DIR", str(runs_root))
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_ENABLED", "1")
    monkeypatch.setenv("ZAKUPKI_GOV_RU_SOAP_TOKEN", "test-token-value-not-real")
    clear_zakupki_soap_settings_cache()

    class FakeClient:
        def __init__(self, _settings):
            pass

        def get_docs_by_reestr_number(self, _reestr_number, subsystem_type="PRIZ"):
            return DocsArchiveResult(
                request_id="req-003",
                ref_id="ref-003",
                archive_url="https://int44.zakupki.gov.ru/archive/demo.zip",
                status="completed",
                warnings=[],
                safe_diagnostic={"archive_url_present": True},
            )

        def download_archive(self, _archive_url, target_dir):
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "documentation-archive.zip").write_bytes(b"PK\x03\x04demo")
            return DownloadedAttachment(
                file_name="demo.zip",
                stored_name="documentation-archive.zip",
                size_bytes=10,
                content_type="application/zip",
                source_url_host="int44.zakupki.gov.ru",
                source_url_path="/archive/demo.zip",
            )

    monkeypatch.setattr(service, "ZakupkiSoapClient", FakeClient)
    monkeypatch.setattr(
        service,
        "_extract_safe_archive_into_run",
        lambda run_id, _path: ([], [], 0),
    )

    response = client.post(
        "/api/demo/tender-agent/runs/from-eis-docs-archive",
        json={"reestr_number": "0888200000224000038", "law": "44fz", "subsystem_type": "PRIZ", "download_archive": False},
    )
    assert response.status_code == 200
    clear_zakupki_soap_settings_cache()

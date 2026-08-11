from desktop.bridge import CVMBridge


def test_open_company_excel_mapping_window_delegates_valid_cvm_id() -> None:
    bridge = CVMBridge()
    opened: list[int] = []
    bridge.set_excel_mapping_window_opener(
        lambda cd_cvm: opened.append(cd_cvm) or {"ok": True},
    )

    assert bridge.open_company_excel_mapping_window({"cd_cvm": 9512}) == {"ok": True}
    assert opened == [9512]

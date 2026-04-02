from pathlib import Path

from resolume_mcp.advanced_output_xml import (
    AdvancedOutputPreferences,
    SliceInspectorPreferences,
    backup_xml_file,
    diff_xml_text,
    export_advanced_output_bundle,
    preview_restore_advanced_output_bundle,
    rename_screen_in_advanced_output,
    rename_slice_in_advanced_output,
    restore_advanced_output_bundle,
    set_advanced_output_soft_edge_power,
    set_advanced_output_screen_output_device,
    set_advanced_output_slice_vertices,
    windows_advanced_output_path_candidates,
)


ADVANCED_OUTPUT_XML = """<?xml version="1.0" encoding="utf-8"?>
<ScreenSetup name="ScreenSetup">
  <versionInfo name="Resolume Arena" majorVersion="7" minorVersion="25" microVersion="3" revision="2905"/>
  <CurrentCompositionTextureSize width="1920" height="1080"/>
  <screens>
    <Screen name="Screen 1" uniqueId="1">
      <Params name="Params">
        <Param name="Name" T="STRING" default="" value="Screen 1"/>
      </Params>
      <guides>
        <ScreenGuide name="ScreenGuide" type="0"/>
      </guides>
      <layers>
        <Slice uniqueId="2">
          <Params name="Common">
            <Param name="Name" T="STRING" default="Layer" value="Slice A"/>
          </Params>
          <InputRect orientation="0">
            <v x="0" y="0"/>
            <v x="1920" y="0"/>
          </InputRect>
          <OutputRect orientation="0">
            <v x="0" y="0"/>
            <v x="1920" y="0"/>
          </OutputRect>
          <Warper>
            <BezierWarper controlWidth="4" controlHeight="4">
              <vertices>
                <v x="0" y="0"/>
                <v x="10" y="10"/>
              </vertices>
            </BezierWarper>
            <Homography>
              <src>
                <v x="0" y="0"/>
              </src>
              <dst>
                <v x="5" y="5"/>
              </dst>
            </Homography>
          </Warper>
        </Slice>
      </layers>
      <OutputDevice>
        <OutputDeviceVirtual name="Screen 1" deviceId="VirtualScreen 1" width="1920" height="1080"/>
      </OutputDevice>
    </Screen>
  </screens>
  <SoftEdging>
    <Params name="Soft Edge">
      <ParamRange name="Power" T="DOUBLE" default="2" value="2.0"/>
    </Params>
  </SoftEdging>
</ScreenSetup>
"""

SLICES_XML = """<?xml version="1.0" encoding="utf-8"?>
<ScreenSetupInspector name="ScreenSetupInspector">
  <versionInfo name="Resolume Arena" majorVersion="7" minorVersion="25" microVersion="3" revision="2905"/>
  <List>
    <Items/>
  </List>
</ScreenSetupInspector>
"""


def test_advanced_output_preferences_summary(tmp_path: Path):
    xml_path = tmp_path / "AdvancedOutput.xml"
    xml_path.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")

    summary = AdvancedOutputPreferences.load(xml_path).summary()
    assert summary["screen_count"] == 1
    assert summary["soft_edge_power"] == 2.0
    assert summary["screens"][0]["slice_count"] == 1
    assert summary["screens"][0]["slices"][0]["name"] == "Slice A"


def test_slices_inspector_summary(tmp_path: Path):
    xml_path = tmp_path / "slices.xml"
    xml_path.write_text(SLICES_XML, encoding="utf-8")

    summary = SliceInspectorPreferences.load(xml_path).summary()
    assert summary["root_tag"] == "ScreenSetupInspector"
    assert summary["item_count"] == 0


def test_backup_xml_file(tmp_path: Path):
    source = tmp_path / "AdvancedOutput.xml"
    source.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")

    result = backup_xml_file(source, tmp_path / "backups")
    assert Path(result["backup"]).exists()
    assert Path(result["backup"]).read_text(encoding="utf-8") == ADVANCED_OUTPUT_XML


def test_diff_xml_text_reports_changes():
    diff = diff_xml_text(
        "<root><a>1</a></root>\n",
        "<root><a>2</a></root>\n",
        current_name="current.xml",
        other_name="other.xml",
    )
    assert diff[0] == "--- current.xml"
    assert any(line.startswith("+<root><a>2</a></root>") for line in diff)


def test_export_advanced_output_bundle(tmp_path: Path):
    advanced_output = tmp_path / "AdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    payload = export_advanced_output_bundle(
        advanced_output_xml_path=advanced_output,
        slices_xml_path=slices_xml,
        export_dir=tmp_path / "exports",
    )
    assert Path(payload["advanced_output_xml"]["export"]).exists()
    assert Path(payload["slices_xml"]["export"]).exists()


def test_preview_restore_advanced_output_bundle(tmp_path: Path):
    current_advanced_output = tmp_path / "CurrentAdvancedOutput.xml"
    current_slices = tmp_path / "CurrentSlices.xml"
    candidate_advanced_output = tmp_path / "CandidateAdvancedOutput.xml"
    candidate_slices = tmp_path / "CandidateSlices.xml"
    current_advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    current_slices.write_text(SLICES_XML, encoding="utf-8")
    candidate_advanced_output.write_text(ADVANCED_OUTPUT_XML.replace("Slice A", "Slice B"), encoding="utf-8")
    candidate_slices.write_text(SLICES_XML.replace("<Items/>", "<Items><Item/></Items>"), encoding="utf-8")

    payload = preview_restore_advanced_output_bundle(
        current_advanced_output_xml_path=current_advanced_output,
        current_slices_xml_path=current_slices,
        candidate_advanced_output_xml_path=candidate_advanced_output,
        candidate_slices_xml_path=candidate_slices,
    )
    assert payload["diffs"]["advanced_output_xml"]["diff_line_count"] > 0
    assert payload["diffs"]["slices_xml"]["diff_line_count"] > 0


def test_restore_advanced_output_bundle(tmp_path: Path):
    current_advanced_output = tmp_path / "AdvancedOutput.xml"
    current_slices = tmp_path / "slices.xml"
    source_advanced_output = tmp_path / "SourceAdvancedOutput.xml"
    source_slices = tmp_path / "SourceSlices.xml"
    current_advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    current_slices.write_text(SLICES_XML, encoding="utf-8")
    source_advanced_output.write_text(ADVANCED_OUTPUT_XML.replace("Slice A", "Slice Restored"), encoding="utf-8")
    source_slices.write_text(SLICES_XML.replace("<Items/>", "<Items><Item/></Items>"), encoding="utf-8")

    payload = restore_advanced_output_bundle(
        current_advanced_output_xml_path=current_advanced_output,
        current_slices_xml_path=current_slices,
        source_advanced_output_xml_path=source_advanced_output,
        source_slices_xml_path=source_slices,
        backup_dir=tmp_path / "backups",
    )
    assert Path(payload["backups"]["advanced_output_xml"]["backup"]).exists()
    assert "Slice Restored" in current_advanced_output.read_text(encoding="utf-8")


def test_windows_advanced_output_path_candidates():
    payload = windows_advanced_output_path_candidates(username="VJ", drive="D:")
    assert payload["documents_root"] == "D:\\Users\\VJ\\Documents\\Resolume Arena"
    assert payload["advanced_output_xml_path"].endswith("AdvancedOutput.xml")


def test_rename_screen_in_advanced_output(tmp_path: Path):
    advanced_output = tmp_path / "AdvancedOutput.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")

    payload = rename_screen_in_advanced_output(
        advanced_output_xml_path=advanced_output,
        screen_index=0,
        new_name="Main Wall",
        backup_dir=tmp_path / "backups",
    )
    assert Path(payload["backup"]["backup"]).exists()
    assert "Main Wall" in advanced_output.read_text(encoding="utf-8")


def test_rename_slice_in_advanced_output(tmp_path: Path):
    advanced_output = tmp_path / "AdvancedOutput.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")

    payload = rename_slice_in_advanced_output(
        advanced_output_xml_path=advanced_output,
        screen_index=0,
        slice_index=0,
        new_name="Slice Main",
        backup_dir=tmp_path / "backups",
    )
    assert Path(payload["backup"]["backup"]).exists()
    assert "Slice Main" in advanced_output.read_text(encoding="utf-8")


def test_set_advanced_output_soft_edge_power(tmp_path: Path):
    advanced_output = tmp_path / "AdvancedOutput.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")

    payload = set_advanced_output_soft_edge_power(
        advanced_output_xml_path=advanced_output,
        value=3.5,
        backup_dir=tmp_path / "backups",
    )
    assert Path(payload["backup"]["backup"]).exists()
    assert 'value="3.5"' in advanced_output.read_text(encoding="utf-8")


def test_set_advanced_output_screen_output_device(tmp_path: Path):
    advanced_output = tmp_path / "AdvancedOutput.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")

    payload = set_advanced_output_screen_output_device(
        advanced_output_xml_path=advanced_output,
        screen_index=0,
        name="LED Wall",
        device_id="\\\\.\\DISPLAY3",
        width=3840,
        height=1080,
        backup_dir=tmp_path / "backups",
    )
    text = advanced_output.read_text(encoding="utf-8")
    assert Path(payload["backup"]["backup"]).exists()
    assert 'name="LED Wall"' in text
    assert 'width="3840"' in text


def test_set_advanced_output_slice_vertices(tmp_path: Path):
    advanced_output = tmp_path / "AdvancedOutput.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")

    payload = set_advanced_output_slice_vertices(
        advanced_output_xml_path=advanced_output,
        screen_index=0,
        slice_index=0,
        path="./OutputRect",
        vertices=[
            {"x": 10.0, "y": 20.0},
            {"x": 100.0, "y": 20.0},
        ],
        backup_dir=tmp_path / "backups",
    )
    text = advanced_output.read_text(encoding="utf-8")
    assert Path(payload["backup"]["backup"]).exists()
    assert 'x="10.0" y="20.0"' in text


def test_set_advanced_output_slice_vertices_rejects_wrong_count(tmp_path: Path):
    advanced_output = tmp_path / "AdvancedOutput.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")

    try:
        set_advanced_output_slice_vertices(
            advanced_output_xml_path=advanced_output,
            screen_index=0,
            slice_index=0,
            path="./Warper/Homography/dst",
            vertices=[{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}],
            backup_dir=tmp_path / "backups",
        )
    except ValueError as exc:
        assert "Vertex count mismatch" in str(exc)
    else:
        raise AssertionError("Expected a vertex count mismatch error.")

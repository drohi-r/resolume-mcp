from pathlib import Path

from resolume_mcp.advanced_output_xml import (
    AdvancedOutputPreferences,
    SliceInspectorPreferences,
    backup_xml_file,
    diff_xml_text,
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

$data = Get-Content 'outputs\rust_parse_test.json' -Raw | ConvertFrom-Json -Depth 100
function Walk($node, [ref]$unknownCount, [ref]$matches) {
  if ($null -eq $node) { return }
  if ($node -is [System.Collections.IEnumerable] -and -not ($node -is [string])) {
    foreach ($item in $node) { Walk $item ([ref]$unknownCount) ([ref]$matches) }
    return
  }
  if ($node -is [pscustomobject]) {
    $props = $node.PSObject.Properties
    if (($props.Name -contains 'size') -and ($node.size -eq 'unknown')) { $unknownCount.Value++ }
    if ($props.Name -contains 'xml_path') {
      switch ($node.xml_path) {
        '/w:body/w:p[13]' { $matches.Value += [pscustomobject]@{xml_path=$node.xml_path; size=$node.size} }
        '/w:body/w:p[14]' { $matches.Value += [pscustomobject]@{xml_path=$node.xml_path; size=$node.size} }
        '/w:body/w:p[29]' { $matches.Value += [pscustomobject]@{xml_path=$node.xml_path; size=$node.size} }
      }
    }
    foreach ($p in $props) { Walk $p.Value ([ref]$unknownCount) ([ref]$matches) }
  }
}
$unknown = 0
$matches = @()
Walk $data ([ref]$unknown) ([ref]$matches)
"unknown_count=$unknown"
$matches | ConvertTo-Json -Depth 5

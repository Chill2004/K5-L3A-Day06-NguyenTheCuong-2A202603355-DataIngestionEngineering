# Validate the recorded local experiment without re-running inference or test.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$culture = [System.Globalization.CultureInfo]::InvariantCulture

function Read-Json($relative) {
    Get-Content -LiteralPath (Join-Path $root $relative) -Raw -Encoding UTF8 | ConvertFrom-Json
}
function Read-JsonLines($relative) {
    @(Get-Content -LiteralPath (Join-Path $root $relative) -Encoding UTF8 |
        Where-Object { $_.Trim() } | ForEach-Object { $_ | ConvertFrom-Json })
}
function Read-Csv($relative) {
    @(Import-Csv -LiteralPath (Join-Path $root $relative))
}
function Require($condition, $message) {
    if (-not $condition) { throw $message }
}
function Normalize($value) { [regex]::Replace($value, '\s+', ' ').Trim() }
function Format-Number($value) { ([double]$value).ToString('0.000', $culture) }

$config = Read-Json 'artifacts/strategies.json'
$manifest = Read-Json 'data/manifest.json'
$source = $manifest.sources[0]
$questions = @(Read-JsonLines 'benchmark/questions.jsonl')
Require ($questions.Count -eq 20) 'Expected 20 questions'
Require (@($questions.id | Select-Object -Unique).Count -eq 20) 'Duplicate question IDs'
Require (@($questions | Where-Object split -eq 'dev').Count -eq 15) 'Expected 15 dev'
Require (@($questions | Where-Object split -eq 'test').Count -eq 5) 'Expected 5 test'
Require (@($questions | Where-Object filter).Count -ge 3) 'Missing filter questions'
Require (@($questions | Where-Object { $_.split -eq 'test' -and $_.filter }).Count -ge 1) 'Missing test filter'

$pages = @(Read-JsonLines 'results/pages.jsonl')
$units = @(Read-JsonLines 'results/sections.jsonl')
Require ($pages.Count -eq 39 -and $units.Count -eq 40) 'Source counts mismatch'
$chars = ($pages | ForEach-Object { $_.text.Length } | Measure-Object -Sum).Sum
$manifestChars = ($source.character_counts.PSObject.Properties | ForEach-Object Value | Measure-Object -Sum).Sum
Require ($chars -eq $manifestChars) 'Manifest character total mismatch'
foreach ($p in $pages) {
    Require ($source.included_pages -contains $p.page) 'Unexpected content page'
    Require ($p.text.Length -eq $source.character_counts.([string]$p.page)) 'Per-page characters mismatch'
}
foreach ($q in $questions) {
    $evidence = Normalize $q.evidence_quote
    $matched = $false
    foreach ($u in $units) {
        if ($u.document_id -cne $q.gold_source_id -or $u.page -ne $q.gold_page) { continue }
        if ($q.filter -and $u.metadata.section -cne $q.filter.section) { continue }
        if ((Normalize $u.text).Contains($evidence)) { $matched = $true }
    }
    Require ($evidence.Length -gt 0 -and $matched) "Evidence mismatch: $($q.id)"
}

$stats = @(Read-Csv 'results/chunk_stats.csv')
$originalRuns = Read-Json 'results/embedding_runs.json'
$timingRuns = Read-Json 'results/reproduced/embedding_runs.json'
$dbRuns = Read-Json 'results/reproduced/database_ingest_runs.json'
$prepare = Read-Json 'results/reproduced/preparation_run.json'
$pdfHash = (Get-FileHash -LiteralPath (Join-Path $root $source.local_path) -Algorithm SHA256).Hash.ToLowerInvariant()
Require ($pdfHash -ceq $prepare.pdf_sha256) 'PDF snapshot hash mismatch'
foreach ($s in 'A', 'B') {
    $chunks = @(Read-JsonLines "results/chunks_$s.jsonl")
    $reproduced = @(Read-JsonLines "results/reproduced/chunks_$s.jsonl")
    $run = $originalRuns | Where-Object strategy -eq $s
    $timing = $timingRuns | Where-Object strategy -eq $s
    $hash = (Get-FileHash (Join-Path $root "results/chunks_$s.jsonl") -Algorithm SHA256).Hash.ToLowerInvariant()
    Require ($hash -ceq $run.input_sha256 -and $hash -ceq $timing.input_sha256) 'Embedding chunk hash mismatch'
    Require ($timing.revision -ceq $config.shared.embedding_revision) 'Model revision mismatch'
    Require ($chunks.Count -eq $reproduced.Count) 'Reproduced chunk count mismatch'
    for ($i = 0; $i -lt $chunks.Count; $i++) {
        Require ($chunks[$i].chunk_id -ceq $reproduced[$i].chunk_id -and $chunks[$i].text -ceq $reproduced[$i].text) 'Reproduced chunk mismatch'
    }
    $st = $stats | Where-Object strategy -eq $s
    Require ($chunks.Count -eq [int]$st.chunk_count) 'Chunk stats count mismatch'
    Require (($chunks | ForEach-Object { $_.text.Length } | Measure-Object -Sum).Sum -eq [int]$st.total_chars) 'Chunk stats total mismatch'
    foreach ($relative in "results/vectors_$s.jsonl", "results/reproduced/vectors_$s.jsonl") {
        $vectors = @(Read-JsonLines $relative)
        Require ($vectors.Count -eq $chunks.Count) 'Vector count mismatch'
        $ids = @{}
        foreach ($c in $chunks) { $ids[$c.chunk_id] = $true }
        foreach ($v in $vectors) {
            Require ($ids.ContainsKey($v.chunk_id)) 'Duplicate or unmatched vector ID'
            $ids.Remove($v.chunk_id)
            Require ($v.embedding.Count -eq 384) 'Wrong vector dimensions'
            $norm = 0.0
            foreach ($x in $v.embedding) {
                Require (-not [double]::IsNaN($x) -and -not [double]::IsInfinity($x)) 'Non-finite vector'
                $norm += $x * $x
            }
            Require ([Math]::Abs($norm - 1.0) -lt 0.001) 'Vector is not unit-normalized'
        }
    }
}

foreach ($split in 'dev', 'test') {
    $traces = @(Read-JsonLines "results/${split}_traces.jsonl")
    $metrics = @(Read-Csv "results/${split}_metrics.csv")
    $expected = if ($split -eq 'dev') { 15 } else { 5 }
    Require ($traces.Count -eq 3 * $expected) 'Wrong trace count'
    foreach ($s in 'A', 'B', 'C') {
        $subset = @($traces | Where-Object strategy -eq $s)
        Require ($subset.Count -eq $expected -and @($subset.question_id | Select-Object -Unique).Count -eq $expected) 'Trace duplicates'
        $n1 = 0; $n3 = 0
        foreach ($t in $subset) {
            $q = $questions | Where-Object id -eq $t.question_id
            Require ($q.split -eq $split -and $t.split -eq $split) 'Wrong split'
            Require ($t.hits.Count -eq 3) 'Missing top-3 hits'
            $flags = @()
            foreach ($h in $t.hits) {
                $hit = $h.document_id -ceq $q.gold_source_id -and $h.page -eq $q.gold_page -and (Normalize $h.text).Contains((Normalize $q.evidence_quote))
                Require ($hit -eq $h.is_hit) 'Stored hit label mismatch'
                $flags += $hit
            }
            Require ($flags[0] -eq $t.hit_at_1 -and ($flags -contains $true) -eq $t.evidence_hit_at_3) 'Trace metric mismatch'
            if ($flags[0]) { $n1++ }; if ($flags -contains $true) { $n3++ }
        }
        $metric = $metrics | Where-Object strategy -eq $s
        Require ($metric.hit1_fraction -ceq "$n1/$expected" -and $metric.hit3_fraction -ceq "$n3/$expected") 'CSV metric mismatch'
    }
}

$coherence = @(Read-Csv 'results/coherence_labels.csv')
$grounding = @(Read-Csv 'results/grounding_labels.csv')
$metadata = @(Read-Csv 'results/metadata_audit.csv')
$filter = @(Read-Csv 'results/test_filter_compliance.csv')
$summary = @()
foreach ($s in 'A', 'B', 'C') {
    $co = @($coherence | Where-Object strategy -eq $s)
    $gr = @($grounding | Where-Object strategy -eq $s)
    $me = @($metadata | Where-Object strategy -eq $s)
    Require ($co.Count -eq 10 -and $gr.Count -eq 5 -and $me.Count -eq 15) 'Audit row count mismatch'
    Require (@($co | Where-Object { $_.coherence_score -notin '0','1','2' }).Count -eq 0) 'Invalid coherence score'
    Require (@($gr | Where-Object { $_.grounding_score -notin '0','1','2' }).Count -eq 0) 'Invalid grounding score'
    $d = Read-Csv 'results/dev_metrics.csv' | Where-Object strategy -eq $s
    $t = Read-Csv 'results/test_metrics.csv' | Where-Object strategy -eq $s
    $base = if ($s -eq 'C') { 'B' } else { $s }
    $st = $stats | Where-Object strategy -eq $base
    $e = $timingRuns | Where-Object strategy -eq $base
    $db = $dbRuns | Where-Object strategy -eq $base
    $f = $filter | Where-Object strategy -eq $s
    $summary += [pscustomobject][ordered]@{
        strategy=$s; dev_hit1=$d.hit1_fraction; dev_hit3=$d.hit3_fraction
        test_hit1=$t.hit1_fraction; test_hit3=$t.hit3_fraction
        chunk_count=$st.chunk_count; total_chars=$st.total_chars
        coherence_mean=($co | Measure-Object coherence_score -Average).Average.ToString($culture)
        grounding_mean=($gr | Measure-Object grounding_score -Average).Average.ToString($culture)
        grounding_0=@($gr | Where-Object grounding_score -eq '0').Count
        grounding_1=@($gr | Where-Object grounding_score -eq '1').Count
        grounding_2=@($gr | Where-Object grounding_score -eq '2').Count
        metadata_correct="$(@($me | Where-Object metadata_complete_correct -eq 'true').Count)/$($me.Count)"
        test_filter_compliance=$f.fraction
        embedding_seconds_for_base=(Format-Number $e.embedding_seconds)
        db_write_seconds_for_base=(Format-Number $db.database_write_seconds)
        resource_note=if($s -eq 'C'){'Reuses B; listed times are B base, not additional cost'}else{'Latest reproduced run, phase timings only'}
        paid_api_cost=0
    }
}
$summary | Export-Csv (Join-Path $root 'results/final_summary.csv') -NoTypeInformation -Encoding UTF8
$critical = @('data/manifest.json','benchmark/questions.jsonl','artifacts/strategies.json',
    'artifacts/selection_decision.md','results/dev_traces.jsonl','results/test_traces.jsonl',
    'results/coherence_labels.csv','results/grounding_labels.csv','results/metadata_audit.csv',
    'results/dev_manual_review.csv','results/reproduced/embedding_runs.json',
    'results/reproduced/database_ingest_runs.json')
$hashes = foreach ($relative in $critical) {
    [pscustomobject]@{path=$relative;sha256=(Get-FileHash (Join-Path $root $relative) -Algorithm SHA256).Hash.ToLowerInvariant()}
}
[ordered]@{
    checked_at_utc=[DateTime]::UtcNow.ToString('o'); status='passed'
    scope='Saved artifact integrity and metric recomputation; no fresh Python/model/database execution'
    content_pages=$pages.Count;source_units=$units.Count;source_characters=$chars
    benchmark_count=$questions.Count; pdf_sha256=$pdfHash
    audit_note='AI-assisted labels; this verification does not constitute independent human review'
    submission_ready=$false
    unresolved=@('Data usage/sharing permission','Exact benchmark and detailed evidence access for grader','Student label review and final commit/submission')
    file_hashes=@($hashes)
} | ConvertTo-Json -Depth 8 | Set-Content (Join-Path $root 'results/verification_report.json') -Encoding UTF8
$summary | Format-Table strategy,dev_hit3,test_hit3,embedding_seconds_for_base,db_write_seconds_for_base
Write-Output 'Saved artifact verification: OK (not a fresh end-to-end execution).'

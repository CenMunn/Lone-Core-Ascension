param([ValidateSet('text','image','poll')][string]$Kind='text',[string]$TaskId='')
$ErrorActionPreference='Stop'
# Run at project root. curl.exe avoids PowerShell's curl alias.
if ($Kind -eq 'text') {
    if (-not $env:DEEPSEEK_API_KEY) { throw 'Set DEEPSEEK_API_KEY first' }
    $textBase=if($env:DEEPSEEK_BASE_URL){$env:DEEPSEEK_BASE_URL.TrimEnd('/')}else{'https://api.deepseek.com'}
    python -m examples.common text --output examples/text.request.json
    curl.exe --fail-with-body --max-time 60 "$textBase/chat/completions" -H "Authorization: Bearer $env:DEEPSEEK_API_KEY" -H 'Content-Type: application/json' --data-binary '@examples/text.request.json'
} else {
    if (-not $env:DASHSCOPE_API_KEY) { throw 'Set DASHSCOPE_API_KEY first' }
    $imageBase=if($env:DASHSCOPE_BASE_URL){$env:DASHSCOPE_BASE_URL.TrimEnd('/')}else{'https://dashscope.aliyuncs.com/api/v1'}
    if($Kind -eq 'image'){
        python -m examples.common image --output examples/image.request.json
        curl.exe --fail-with-body --max-time 60 "$imageBase/services/aigc/text2image/image-synthesis" -H "Authorization: Bearer $env:DASHSCOPE_API_KEY" -H 'X-DashScope-Async: enable' -H 'Content-Type: application/json' --data-binary '@examples/image.request.json'
    } else {
        if($TaskId -notmatch '^[A-Za-z0-9_-]{1,128}$'){throw 'A valid task ID is required'}
        curl.exe --fail-with-body --max-time 60 "$imageBase/tasks/$TaskId" -H "Authorization: Bearer $env:DASHSCOPE_API_KEY"
    }
}

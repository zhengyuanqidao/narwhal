#!/usr/bin/env bash
# 重新拉取真实网络语料（eval/fixtures/web/）。用法: bash eval/fixtures/web/fetch.sh
# 注意：第三方内容仅本地测试用，不进仓库分发。
set -u
cd "$(dirname "$0")" || exit 1

dl() {
  url="$1"; out="$2"
  code=$(curl -sSL -m 90 --retry 2 -w "%{http_code}" -o "$out" "$url" 2>/dev/null)
  if [ "$code" = "200" ]; then
    echo "  ok  $(du -h "$out" | cut -f1)  $out"
  else
    echo "  FAIL($code)  $out  <- $url"; rm -f "$out"
  fi
}

dl "https://raw.githubusercontent.com/github/gitignore/main/Python.gitignore" "01-Python.gitignore.txt"
dl "https://raw.githubusercontent.com/OAI/OpenAPI-Specification/main/versions/3.0.3.md" "02-openapi-3.0.3.md"
dl "https://paulgraham.com/greatwork.html" "03-paulgraham-greatwork.html"
dl "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv" "04-iris.csv"
dl "https://export.arxiv.org/pdf/1706.03762v7" "05-1706.03762.pdf"
dl "https://raw.githubusercontent.com/danluu/post-mortems/master/README.md" "06-postmortems-collection.md"
dl "https://raw.githubusercontent.com/ruanyf/weekly/master/README.md" "07-ruanyf-weekly-README.md"
dl "https://raw.githubusercontent.com/jgm/pandoc/main/test/docx/inline_formatting.docx" "08-inline_formatting.docx"
dl "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/SampleSS.xlsx" "09-sample-spreadsheet.xlsx"
dl "https://raw.githubusercontent.com/apache/poi/trunk/test-data/slideshow/45541_Footer.pptx" "10-sample-slideshow.pptx"
dl "https://raw.githubusercontent.com/expressjs/express/master/package.json" "11-express-package.json"
dl "https://raw.githubusercontent.com/actions/starter-workflows/main/ci/node.js.yml" "12-github-actions-node.yml"
dl "https://raw.githubusercontent.com/python/cpython/main/Lib/test/test_email/data/msg_02.txt" "13-email-sample.eml"

echo "--- 校验（与 MANIFEST 对照）---"
for f in *; do [ -f "$f" ] && [ "$f" != "fetch.sh" ] && printf "%-34s %s\n" "$f" "$(shasum -a 256 "$f" | cut -c1-16)"; done

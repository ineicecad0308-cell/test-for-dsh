# -*- coding: utf-8 -*-
"""本地 Web 界面：填表 -> 抓取 -> 下载 Excel。

启动：python web.py [--port 8765]
浏览器打开 http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(BASE, "platforms"))

from excel_export import default_filename, export  # noqa: E402
from models import FilterConfig  # noqa: E402
from platforms.base import available_platforms  # noqa: E402
from scraper import run  # noqa: E402

OUT_ROOT = os.path.join(BASE, "output")
os.makedirs(OUT_ROOT, exist_ok=True)

CITY_HINT = "上海、北京、深圳、广州、杭州、成都、苏州、武汉、南京、西安、广东、江苏、浙江…"

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>招聘岗位要求抓取器</title>
<style>
:root{--main:#1f4e79;--bg:#f5f7fa;--line:#d8e0ea;}
*{box-sizing:border-box}
body{margin:0;font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif;background:var(--bg);color:#1b1f24}
header{background:var(--main);color:#fff;padding:20px 28px}
header h1{margin:0;font-size:20px;font-weight:600}
header p{margin:6px 0 0;font-size:13px;opacity:.85}
main{max-width:980px;margin:22px auto 60px;padding:0 18px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:22px 24px;box-shadow:0 1px 3px rgba(16,24,40,.05)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px 22px}
.field{display:flex;flex-direction:column;gap:6px}
.field label{font-size:13px;font-weight:600}
.field small{color:#667085;font-size:12px}
input,select{height:36px;border:1px solid var(--line);border-radius:7px;padding:0 10px;font-size:14px;background:#fff}
input:focus,select:focus{outline:2px solid #9cc3e5;border-color:#9cc3e5}
.full{grid-column:1/-1}
.actions{margin-top:20px;display:flex;align-items:center;gap:14px}
button{background:var(--main);color:#fff;border:0;border-radius:8px;height:42px;padding:0 26px;font-size:15px;cursor:pointer}
button:hover{background:#2a6398}
button:disabled{background:#98a2b3;cursor:progress}
.hint{font-size:12px;color:#667085}
.err{background:#fef3f2;border:1px solid #fda29b;color:#b42318;padding:12px 14px;border-radius:8px;margin-bottom:16px;white-space:pre-wrap}
.ok{background:#ecfdf3;border:1px solid #6ce9a6;color:#05603a;padding:12px 14px;border-radius:8px;margin-bottom:16px}
table{border-collapse:collapse;width:100%;font-size:12.5px;background:#fff}
th,td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
th{background:#eef3f9;font-weight:600}
tr:nth-child(even) td{background:#fafcfe}
.tag{display:inline-block;background:#eef3f9;border-radius:4px;padding:1px 7px;margin:0 6px 6px 0;font-size:12px}
code{background:#eef3f9;padding:1px 6px;border-radius:4px;font-size:12px}
</style></head><body>
<header><h1>招聘岗位要求抓取器</h1>
<p>按平台、岗位、年限、薪资、公司规模、工作地点抓取 JD，拆成单条要求并导出 Excel</p></header>
<main>
@@BODY@@
</main></body></html>"""


def form_html(msg: str = "", error: str = "", values: dict | None = None) -> str:
    v = values or {}

    def val(key, default=""):
        return html.escape(str(v.get(key, default)))

    plats = available_platforms()
    opts = "".join(
        f'<option value="{k}"{" selected" if k == v.get("platform", "liepin") else ""}>{v2}（{k}）</option>'
        for k, v2 in plats.items())
    year_choices = ["3-5", "1-3", "3+", "5+", "不限"]
    ycur = v.get("years", "3-5")
    yopts = "".join(
        f'<option value="{y}"{" selected" if y == ycur else ""}>{y}</option>' for y in year_choices)
    if ycur not in year_choices:
        yopts += f'<option value="{html.escape(ycur)}" selected>{html.escape(ycur)}</option>'
    body = f"""
{('<div class="err">' + html.escape(error) + '</div>') if error else ''}
{msg}
<div class="card">
<form method="post" action="/run" onsubmit="this.querySelector('button').disabled=true;this.querySelector('button').textContent='抓取中，请稍候…（约 1-3 分钟）';">
  <div class="grid">
    <div class="field"><label>招聘平台</label>
      <select name="platform">{opts}</select>
      <small>后续可扩展更多平台，接口已抽象</small></div>
    <div class="field"><label>岗位关键词</label>
      <input name="keyword" value="{val('keyword', 'SAP MM')}" placeholder="如 SAP MM、Java开发、财务经理">
      <small>同时作为搜索词，多个词用空格分隔</small></div>
    <div class="field"><label>经验年限</label>
      <input name="years" value="{val('years', '3-5')}" list="ylist" placeholder="3-5">
      <datalist id="ylist">{yopts}</datalist>
      <small>3-5 表示与岗位年限区间有交集；3+ 表示 3 年以上；不限</small></div>
    <div class="field"><label>月薪范围（千元）</label>
      <input name="salary" value="{val('salary')}" placeholder="如 15-30、20+，留空为不限">
      <small>按 K/月 折算比较，如 15-30 表示 15k-30k</small></div>
    <div class="field"><label>公司规模（人数）</label>
      <input name="people" value="{val('people', '1000+')}" placeholder="如 1000+、500-2000，留空为不限">
      <small>1000+ 表示 1000 人以上</small></div>
    <div class="field"><label>工作地点</label>
      <input name="location" value="{val('location')}" placeholder="如 上海，或 上海,北京，留空为全国">
      <small>{CITY_HINT}</small></div>
    <div class="field"><label>最多导出行数</label>
      <input name="rows" type="number" min="1" max="1000" value="{val('rows', '100')}">
      <small>每个岗位一行（需求内容为职位介绍全文）</small></div>
    <div class="field"><label>同一公司最多几行</label>
      <input name="rows_per_company" type="number" min="1" max="50" value="{val('rows_per_company', '3')}">
      <small>用于控制单家公司的占比</small></div>
    <div class="field"><label>岗位名称必备词</label>
      <input name="require" value="{val('require', '')}" placeholder="如 SAP,MM；留空=不限制">
      <small>须出现在岗位名称中，多个用逗号分隔</small></div>
    <div class="field full"><label>排除关键词</label>
      <input name="exclude" value="{val('exclude', '')}" placeholder="如 实习,外包,销售；留空=不排除">
      <small>命中岗位名称则丢弃</small></div>
  </div>
  <div class="actions">
    <button type="submit">开始抓取并生成 Excel</button>
    <span class="hint">抓取会比较慢，请勿关闭页面；结果生成后会自动下载。</span>
  </div>
</form>
</div>
"""
    return PAGE.replace("@@BODY@@", body)


def result_html(res, filename: str) -> str:
    rows = res.rows[:30]
    trs = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(r.get("序号", ""))), html.escape(str(r.get("公司名称", ""))),
            html.escape(str(r.get("岗位名称", ""))), html.escape(str(r.get("工作地点", ""))),
            html.escape(str(r.get("经验要求", ""))), html.escape(str(r.get("要求类型", ""))),
            html.escape(str(r.get("需求内容", ""))[:160]))
        for r in rows)
    stats = "".join(f'<span class="tag">{html.escape(k)}：{html.escape(str(v))}</span>'
                    for k, v in res.stats.items())
    cond = "".join(f'<span class="tag">{html.escape(k)}：{html.escape(str(v))}</span>'
                   for k, v in res.cfg.summary().items())
    more = (f"<p class='hint'>仅预览前 {len(rows)} 条，完整 {len(res.rows)} 条见 Excel。</p>"
            if len(res.rows) > len(rows) else "")
    body = f"""
<div class="ok">✅ 已生成：<code>{html.escape(filename)}</code>　
<a href="/download/{urllib.parse.quote(filename)}">点击下载 Excel</a>　
<a href="/">再抓一次</a></div>
<div class="card">
  <h3 style="margin-top:0">抓取条件</h3>{cond}
  <h3>统计</h3>{stats}
  <h3>结果预览</h3>
  <table><thead><tr><th>序号</th><th>公司</th><th>岗位</th><th>地点</th><th>经验</th><th>类型</th><th>需求内容</th></tr></thead>
  <tbody>{trs}</tbody></table>
  {more}
</div>"""
    return PAGE.replace("@@BODY@@", body)


def parse_form(form: dict) -> FilterConfig:
    def get(k, d=""):
        return (form.get(k) or [d])[0].strip()

    def years(text):
        t = text.lower().replace("年", "").replace("以上", "+")
        if t in ("", "不限", "any"):
            return None
        if t.endswith("+"):
            return (float(t[:-1]), 99.0)
        if "-" in t:
            a, b = t.split("-", 1)
            return (float(a), float(b))
        n = float(t)
        return (n, n)

    def salary(text):
        t = text.lower().replace("k", "").replace("千", "").replace(" ", "")
        if t in ("", "不限"):
            return None
        mult = 10.0 if "万" in t else 1.0
        t = t.replace("万", "")
        if t.endswith("+"):
            return (float(t[:-1]) * mult, 999.0)
        if "-" in t:
            a, b = t.split("-", 1)
            return (float(a) * mult, float(b) * mult)
        n = float(t) * mult
        return (n, n)

    def people(text):
        t = text.replace("人", "").replace(" ", "")
        if t in ("", "不限"):
            return (None, None)
        if t.endswith("+"):
            return (float(t[:-1]), None)
        if "-" in t:
            a, b = t.split("-", 1)
            return (float(a), None if b.endswith("+") else float(b))
        return (float(t), None)

    locs = [x.strip() for x in re.split(r"[,，、/\s]+", get("location")) if x.strip()]
    rows = int(get("rows", "100") or 100)
    return FilterConfig(
        platform=get("platform", "liepin") or "liepin",
        keyword=get("keyword", "SAP MM"),
        years=years(get("years", "3-5")),
        salary=salary(get("salary")),
        people_min=people(get("people"))[0],
        people_max=people(get("people"))[1],
        locations=locs,
        require_tokens=[t.strip() for t in re.split(r"[,，]", get("require")) if t.strip()],
        exclude_tokens=[t.strip() for t in re.split(r"[,，]", get("exclude")) if t.strip()],
        limit_rows=max(1, min(rows, 1000)),
        max_details=150,
        max_per_company=max(1, min(int(get("rows_per_company", "3") or 3), 50)),
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "JobScraper/1.0"

    def log_message(self, fmt, *args):  # 静音默认日志
        pass

    def _run_job(self, form, values):
        cfg = parse_form(form)
        if not cfg.keyword:
            raise ValueError("岗位关键词不能为空")
        res = run(cfg, cache_path=os.path.join(BASE, "data", "detail_cache.json"))
        if not res.rows:
            msg = "没有抓到符合条件的要求，可放宽年限/薪资/规模/地点后重试。"
            if res.errors:
                msg += "　提示：" + "；".join(res.errors[:3])
            return None, None, msg
        out = os.path.join(OUT_ROOT, default_filename(cfg))
        export(res, out)
        return res, os.path.basename(out), ""

    def _send(self, code: int, body: str, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, form_html())
            return
        if path.startswith("/download/"):
            name = urllib.parse.unquote(path[len("/download/"):])
            # 只允许 output 目录内的文件名，防止路径穿越
            safe = os.path.basename(name)
            target = os.path.abspath(os.path.join(OUT_ROOT, safe))
            if not target.startswith(os.path.abspath(OUT_ROOT) + os.sep) or not os.path.exists(target):
                self._send(404, "文件不存在")
                return
            size = os.path.getsize(target)
            self.send_response(200)
            self.send_header("Content-Type",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Disposition",
                             "attachment; filename*=UTF-8''" + urllib.parse.quote(safe))
            self.end_headers()
            with open(target, "rb") as f:
                self.wfile.write(f.read())
            return
        self._send(404, "页面不存在")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path != "/run":
            self._send(404, "页面不存在")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        form = urllib.parse.parse_qs(raw)
        values = {k: (v[0] if v else "") for k, v in form.items()}
        try:
            res, name, msg = self._run_job(form, values)
            if res is None:
                self._send(200, form_html(error=msg, values=values))
                return
            self._send(200, result_html(res, name))
        except Exception as e:
            tb = traceback.format_exc()
            self._send(500, form_html(error=f"{e}\n{tb[-600:]}", values=values))


def main() -> None:
    ap = argparse.ArgumentParser(description="招聘岗位要求抓取器 - 本地 Web 界面")
    ap.add_argument("--port", "-p", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"招聘岗位要求抓取器已启动：http://{args.host}:{args.port}")
    print("按 Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()

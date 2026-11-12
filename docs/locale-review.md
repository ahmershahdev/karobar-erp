# Urdu and Arabic review

A review pass over `frontend/src/i18n/locales/ur.json` and `ar.json` on 2026-11-12, by the coding agent, not a native speaker. Clear mistakes were fixed (see the pull request). The phrases below are doubtful and need a native reader before launch. Each line gives the key, what is there now, and the question.

## Checked by script

Every key in English is present in Urdu and Arabic, with the same placeholders. Urdu has no Arabic-only letters (ي ك ه ى) and Arabic has no Urdu-only letters. Latin text left in both files is brand names and codes only: Google, Facebook, GitHub, Groq, reCAPTCHA, EOBI, CNIC, IBAN, SKU, PCS, SIF, MIT, CSV, PNG.

## Arabic

- **The word for "business".** The file uses عمل in about 50 places (عمل جديد, اسم العمل, كيف حال عملي؟) and نشاط تجاري in about 12 (the chat, deleting an account, handing over a business). عمل also means "work", so عمل جديد can read as "a new job". The suggestion is نشاط تجاري everywhere, which needs one pass over the whole file. Decide which word to use.
- **Customer.** Sales screens say الزبون, while chat drafts and bill design hints say العميل. Pick one.
- **Store and warehouse.** Inventory uses المستودع, guides use المخزن, the counter uses المتجر. The English also mixes "store" and "warehouse", so this may be fine.
- **Numbers before nouns.** In Arabic the noun's form depends on the number (3 to 10 take a plural, 11 and above a singular). Where a count is filled in, the fixed text can only be right for some numbers. The simple labels were changed to the form `label: {{n}}`. These sentences still put a number before a noun and need a native reader, or plural forms in code:
  - `payroll.rule.summary`: `{{firstDays}} يوم أجر عن كل سنة من أول {{firstYears}} سنوات، ثم {{laterDays}} يومًا عن كل سنة،`
  - `payroll.rule.minSummary`: `لا شيء مستحق قبل {{years}} سنة.`
  - `payroll.rule.capSummary`: `لا تزيد أبدًا عن أجر {{months}} شهرًا.`
  - `payroll.rule.bandSummary` and `bandSummaryAfter`: `... من {{years}} سنوات ...`
  - `footer.shipped`: `{{count}} من 7 مراحل منجزة`
- **`chat.notice`**: `يحمل كل رسالة توقيعًا` should be `تحمل كل رسالة توقيعًا` (رسالة is feminine). It is fixed after the chat retention pull request (#62) merges, because that pull request changes the same text.
- **`auth.recaptchaNotice`**: the parts join as `تنطبق سياسة الخصوصية و شروط الخدمة من Google.` The و stands apart from the next word because the parts are separate links. Check that it reads acceptably.
- **`pos.less` and `pos.more`**: `واحد أقل` and `واحد أكثر`. Would `أنقص واحدًا` and `زد واحدًا` read better on a button?
- **`account.deleteBody`** writes the app name in Latin letters (Karobar), while the rest of the file writes كاروبار.

## Urdu

- **`workspace.valuation`**: `اسٹاک کی قیمت گذاری`. Is قیمت گذاری the usual spelling, or قیمت گزاری?
- **Units.** Most screens say یونٹ and یونٹس; the guides say اکائی and اکائیاں. Pick one.
- **Sales and reports.** Menu groups say فروخت and رپورٹیں; module names say سیلز and رپورٹس. Both may be fine in their places.
- **`ledger.rows`**: Accounts receivable is `وصولی کھاتہ`. Is `قابل وصول رقوم` clearer?
- **`bill.templates.elegantBody`**: serif type was written `باریک حروف` ("thin letters"), which is not what serif means. Is there a usual Urdu word, or should it just say `خوبصورت حروف`?
- **`pur.againstOrder`** was changed to `{{number}} کے تحت`, and payments to `بلوں میں ایڈجسٹ`. Check these read as normal shop and accounting Urdu.
- **`tax.typeIt`** was `ٹیکس میں خود لکھوں گا`, which is masculine. It is now `ٹیکس خود لکھنا ہے`, so it fits anyone. Check that it reads naturally on a tick box.
- **The assistant speaks as masculine** (`سوچ رہا ہے`, `میں یہ مسودہ نہیں بنا سکا`). Keep or change.
- **`account.deleteBody`** writes the app name in Latin letters (Karobar). Elsewhere کاروبار is used for both the app and "business", which can be ambiguous; the Latin may be deliberate here.

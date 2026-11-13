export const ROLE = { admin: 'מנהל מערכת', manager: 'מנהל', finance: 'כספים', warehouse: 'מחסן', it: 'IT', hr: 'משאבי אנוש', viewer: 'צפייה בלבד' }
export const INVOICE_STATUS = { open: 'פתוחה', partial: 'שולמה חלקית', paid: 'שולמה', cancelled: 'מבוטלת' }
export const DOC_TYPE = { tax_invoice: 'חשבונית מס', tax_invoice_receipt: 'חשבונית מס קבלה', credit_note: 'חשבונית זיכוי', proforma: 'חשבון עסקה' }
export const PAY_METHOD = { bank_transfer: 'העברה בנקאית', credit_card: 'כרטיס אשראי', check: "צ'ק", cash: 'מזומן', bit: 'ביט / פייבוקס', other: 'אחר' }
export const MOVEMENT = { receive: 'קליטה מספק', issue: 'הוצאה / מכירה', adjust: 'תיקון ספירה', transfer: 'העברה בין מחסנים', return: 'החזרה מלקוח' }
export const EMP_STATUS = { active: 'פעיל', offboarding: 'בתהליך עזיבה', left: 'עזב' }
export const ASSET_TYPE = { laptop: 'מחשב נייד', desktop: 'מחשב נייח', monitor: 'מסך', phone: 'טלפון', tablet: 'טאבלט', printer: 'מדפסת', network: 'ציוד רשת', peripheral: 'ציוד היקפי', license: 'רישיון תוכנה', other: 'אחר' }
export const ASSET_STATUS = { in_stock: 'במלאי', assigned: 'מוחזק ע"י עובד', repair: 'בתיקון', retired: 'נגרע', lost: 'אבד / נגנב' }

const nf = new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS', maximumFractionDigits: 2 })
export const money = (v) => (v === null || v === undefined || v === '' ? '—' : nf.format(Number(v)))
export const num = (v) => new Intl.NumberFormat('he-IL').format(Number(v || 0))
export const fdate = (v) => (v ? new Date(v.length === 10 ? v + 'T00:00:00' : v).toLocaleDateString('he-IL') : '—')
export const fdatetime = (v) => (v ? new Date(v.endsWith('Z') || v.includes('+') ? v : v + 'Z').toLocaleString('he-IL') : '—')
export const today = () => new Date().toISOString().slice(0, 10)
export const toOptions = (map) => Object.entries(map).map(([value, label]) => ({ value, label }))

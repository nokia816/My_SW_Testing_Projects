import ResourcePage from '../components/ResourcePage'

const partnerFields = [
  { name: 'name', label: 'שם', required: true },
  { name: 'vat_id', label: 'ח.פ / ע.מ' },
  { name: 'contact_name', label: 'איש קשר' },
  { name: 'phone', label: 'טלפון', type: 'tel', max: 40 },
  { name: 'email', label: 'אימייל', type: 'email' },
  { name: 'address', label: 'כתובת', max: 300 },
]
const partnerCols = [
  { key: 'name', label: 'שם' }, { key: 'vat_id', label: 'ח.פ' }, { key: 'contact_name', label: 'איש קשר' },
  { key: 'phone', label: 'טלפון' }, { key: 'email', label: 'אימייל' },
]

export const Suppliers = () => (
  <ResourcePage title="ספקים" endpoint="/suppliers" resource="suppliers" exportName="suppliers" createLabel="ספק חדש"
    columns={partnerCols} fields={[...partnerFields, { name: 'notes', label: 'הערות', type: 'textarea' }]} />
)

export const Customers = () => (
  <ResourcePage title="לקוחות" endpoint="/customers" resource="customers" exportName="customers" createLabel="לקוח חדש"
    columns={[...partnerCols, { key: 'payment_terms_days', label: 'תנאי תשלום', render: (r) => (r.payment_terms_days ? `שוטף + ${r.payment_terms_days}` : 'מיידי') }]}
    fields={[...partnerFields, { name: 'payment_terms_days', label: 'תנאי תשלום (ימים)', type: 'number', default: 30 },
      { name: 'notes', label: 'הערות', type: 'textarea' }]} />
)

export const Warehouses = () => (
  <ResourcePage title="מחסנים" endpoint="/warehouses" resource="warehouses" createLabel="מחסן חדש"
    columns={[{ key: 'name', label: 'שם' }, { key: 'location', label: 'מיקום' }]}
    fields={[{ name: 'name', label: 'שם', required: true }, { name: 'location', label: 'מיקום', max: 300 }]} />
)

export const Departments = () => (
  <ResourcePage title="מחלקות" endpoint="/departments" resource="departments" createLabel="מחלקה חדשה"
    columns={[{ key: 'name', label: 'שם' }, { key: 'manager_name', label: 'מנהל/ת' }]}
    fields={[{ name: 'name', label: 'שם', required: true }, { name: 'manager_name', label: 'מנהל/ת' }]} />
)

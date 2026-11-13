"""J2: customer CRUD — generated form, searchable/sortable table, edit and delete."""
from dataclasses import dataclass, field, replace
from enum import Enum

from ui4me import ui


class Tier(Enum):
    FREE = "Free"
    PRO = "Pro"
    ENTERPRISE = "Enterprise"


@dataclass
class Customer:
    id: int = 0
    name: str = field(default="", metadata={"label": "Full name", "required": True})
    email: str = field(default="", metadata={"required": True, "pattern": "email"})
    tier: Tier = Tier.FREE
    active: bool = True


customers = ui.state([Customer(1, "Ada Lovelace", "ada@example.com", Tier.PRO),
                      Customer(2, "Alan Turing", "alan@example.com", Tier.ENTERPRISE),
                      Customer(3, "Grace Hopper", "grace@example.com")])
selected = ui.state(None)

with ui.app("Customers", width=1100, height=720) as app:
    def save(customer: Customer):
        if customer.id:
            customers.update(lambda rows: [customer if c.id == customer.id else c for c in rows])
        else:
            customer = replace(customer, id=max((c.id for c in customers.value), default=0) + 1)
            customers.update(lambda rows: [*rows, customer])
        ui.notify(f"Saved {customer.name}", kind="success")
        selected.set(None)
        form.reset(Customer())

    async def delete():
        row = table.selected_row
        if row and await ui.confirm(f"Delete {row.name}?", ok="Delete", danger=True):
            customers.update(lambda rows: [c for c in rows if c.id != row.id])
            selected.set(None)

    ui.heading("Customers", level=1)
    with ui.split(side="380px") as split:
        with split.side, ui.card():
            ui.heading(lambda: "Edit customer" if selected.value else "New customer", level=3)
            form = ui.form(Customer, exclude=["id"], on_submit=save, submit_label="Save customer")
        with split.main:
            table = ui.table(customers, key="id", search=True, sort=True, page_size=12, selected=selected,
                             columns=["name", "email", ("tier", "Plan"), "active"],
                             on_select=lambda c: form.set_value(c))
            ui.button("Delete selected", variant="danger", on_click=delete, disabled=lambda: selected.value is None)
app.run()

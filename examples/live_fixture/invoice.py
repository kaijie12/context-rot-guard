def total(
    subtotal,
    exempt=False,
    *,
    marketplace=False,
    reseller=False,
    home_state=None,
    ship_state=None,
):
    tax_rate = 0.08

    if marketplace:
        return subtotal + subtotal * tax_rate

    if reseller:
        if home_state is not None and home_state == ship_state:
            return subtotal
        return subtotal + subtotal * tax_rate

    if exempt:
        return subtotal

    return subtotal + subtotal * tax_rate
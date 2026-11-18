with supply_costs as (
    select product_id, sum(supply_cost) as supply_cost
    from {{ ref('stg_supplies') }}
    group by product_id
)

select
    i.order_item_id,
    i.order_id,
    i.product_id,
    o.customer_id,
    o.store_id,
    o.ordered_at,
    p.product_price,
    coalesce(s.supply_cost, 0) as supply_cost
from {{ ref('stg_order_items') }} as i
inner join {{ ref('stg_orders') }} as o on i.order_id = o.order_id
inner join {{ ref('stg_products') }} as p on i.product_id = p.product_id
left join supply_costs as s on i.product_id = s.product_id

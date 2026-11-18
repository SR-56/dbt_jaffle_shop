with item_summary as (
    select
        i.order_id,
        count(*) as item_count,
        count(*) filter (where p.product_type = 'jaffle') as food_item_count,
        count(*) filter (where p.product_type = 'beverage') as drink_item_count
    from {{ ref('stg_order_items') }} as i
    inner join {{ ref('stg_products') }} as p on i.product_id = p.product_id
    group by i.order_id
)

select
    o.order_id,
    o.customer_id,
    o.store_id,
    o.ordered_at,
    o.subtotal,
    o.tax_paid,
    o.order_total,
    coalesce(s.item_count, 0) as item_count,
    coalesce(s.food_item_count, 0) > 0 as is_food_order,
    coalesce(s.drink_item_count, 0) > 0 as is_drink_order
from {{ ref('stg_orders') }} as o
left join item_summary as s on o.order_id = s.order_id

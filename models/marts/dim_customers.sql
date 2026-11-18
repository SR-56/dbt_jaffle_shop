with order_stats as (
    select
        customer_id,
        count(*) as lifetime_orders,
        min(ordered_at) as first_ordered_at
    from {{ ref('stg_orders') }}
    group by customer_id
)

select
    c.customer_id,
    c.customer_name,
    s.first_ordered_at,
    coalesce(s.lifetime_orders, 0) as lifetime_orders,
    case when coalesce(s.lifetime_orders, 0) > 1 then 'returning' else 'new' end as customer_type
from {{ ref('stg_customers') }} as c
left join order_stats as s on c.customer_id = s.customer_id

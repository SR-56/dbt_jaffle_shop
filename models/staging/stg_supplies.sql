-- id は同じ備品を表し、商品（sku）ごとに1行ずつある。主キーは (supply_id, product_id)
select
    id as supply_id,
    sku as product_id,
    name as supply_name,
    {{ cents_to_dollars("cost") }} as supply_cost,
    perishable as is_perishable
from {{ ref('raw_supplies') }}

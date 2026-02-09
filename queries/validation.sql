-- Query de validação: itens coletados nas últimas 24 horas
-- Agrupa por fonte e mostra contagens e estatísticas de preço

SELECT
    source,
    COUNT(*) AS total_items,
    COUNT(DISTINCT item_id) AS unique_items,
    ROUND(AVG(price), 2) AS avg_price,
    ROUND(MIN(price), 2) AS min_price,
    ROUND(MAX(price), 2) AS max_price,
    COUNTIF(discount_percent IS NOT NULL) AS items_with_discount,
    ROUND(AVG(discount_percent), 2) AS avg_discount_percent,
    MIN(collected_at) AS first_collected,
    MAX(collected_at) AS last_collected
FROM
    `{project_id}.promozone.promotions`
WHERE
    collected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY
    source
ORDER BY
    total_items DESC;


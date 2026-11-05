<?php
// Run with: wp --path=/var/www/bzbdev/data/www/dev.bzbgear.com eval-file test_dev.php
$id = 126837;
$context = bzb_product_ai_context($id);
echo 'product=' . ($context['sku'] ?? 'none') . ', sections=' . count($context['sections'] ?? []) . ', resources=' . count($context['resources'] ?? []) . ', articles=' . count($context['articles'] ?? []) . PHP_EOL;
foreach ($context['sections'] as $name => $value) echo 'section=' . $name . ', chars=' . mb_strlen($value) . PHP_EOL;
$variable = get_posts(['post_type' => 'product', 'post_status' => 'publish', 'posts_per_page' => 100, 'fields' => 'ids']);
foreach ($variable as $candidate) {
    $product = wc_get_product($candidate);
    if ($product && $product->is_type('variable')) {
        $vctx = bzb_product_ai_context($candidate);
        echo 'variable=' . $vctx['sku'] . ', variants=' . count($vctx['variant_skus']) . PHP_EOL;
        break;
    }
}
foreach ([
    [$id, 'Where can I find the manual and connection diagram?'],
    [$id, 'What are the specifications of BG-ADAMO-4K?'],
    [$candidate, 'What variations does this product have?'],
] as [$product_id, $question]) {
    $request = new WP_REST_Request('POST', '/bzb-product-ai/v1/ask');
    $request->set_header('X-WP-Nonce', wp_create_nonce('wp_rest'));
    $request->set_body_params(['product_id' => $product_id, 'question' => $question]);
    $response = rest_do_request($request);
    echo 'question=' . $question . ', status=' . $response->get_status() . PHP_EOL;
    echo wp_json_encode($response->get_data(), JSON_UNESCAPED_SLASHES) . PHP_EOL;
}

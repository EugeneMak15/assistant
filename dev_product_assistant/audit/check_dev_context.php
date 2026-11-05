<?php
// Read-only verification of Dev assistant's per-product article context.
$skus = ['BG-4K-VP1616PRO','BG-IPGEAR-PRO','BG-UHD-VWP110L','BG-EXH-8K100U',
    'BG-EXH-8K50C','BG-EXH-4KFE','BG-8KCH'];
$out = [];
foreach ($skus as $sku) {
    $id = wc_get_product_id_by_sku($sku);
    $product = wc_get_product($id);
    $variant_skus = [];
    if ($product && $product->is_type('variable')) foreach ($product->get_children() as $child_id) {
        $child = wc_get_product($child_id);
        if ($child && $child->get_status() === 'publish' && $child->get_sku()) $variant_skus[] = $child->get_sku();
    }
    delete_transient('bzb_product_ai_articles_' . md5(implode('|', array_merge([$sku], $variant_skus))));
    $context = function_exists('bzb_product_ai_context') ? bzb_product_ai_context($id) : null;
    $articles = [];
    foreach (($context['articles'] ?? []) as $article) {
        $post_id = url_to_postid($article['url']);
        $articles[] = ['title' => $article['title'], 'type' => get_post_type($post_id), 'url' => $article['url']];
    }
    $out[] = ['sku' => $sku, 'id' => $id, 'articles' => $articles];
}
echo wp_json_encode($out, JSON_UNESCAPED_SLASHES);

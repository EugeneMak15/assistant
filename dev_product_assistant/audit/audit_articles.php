<?php
// Read-only exact-SKU mentions in public non-product WordPress content.
$skus = ['BG-4K-VP1616PRO','BG-IPGEAR-PRO','BG-IPGEAR-PRO-T','BG-IPGEAR-PRO-R',
    'BG-UHD-VWP110L','BG-EXH-8K100U','BG-EXH-8K50C','BG-EXH-4KFE','BG-8KCH'];
global $wpdb;
$results = [];
foreach ($skus as $sku) {
    $like = '%' . $wpdb->esc_like($sku) . '%';
    $ids = $wpdb->get_col($wpdb->prepare(
        "SELECT ID FROM {$wpdb->posts} WHERE post_status='publish' AND post_type NOT IN ('product','product_variation','attachment','page') AND (post_title LIKE %s OR post_content LIKE %s) LIMIT 100",
        $like, $like));
    $pattern = '/(?<![A-Za-z0-9_-])' . preg_quote($sku, '/') . '(?![A-Za-z0-9_-])/i';
    $matches = [];
    foreach ($ids as $id) {
        $post = get_post($id);
        if (!$post || !is_post_type_viewable($post->post_type)) continue;
        $text = wp_strip_all_tags($post->post_content);
        if (!preg_match($pattern, $post->post_title . ' ' . $text)) continue;
        $matches[] = ['type' => $post->post_type, 'title' => get_the_title($id), 'url' => get_permalink($id)];
    }
    $results[$sku] = $matches;
}
echo wp_json_encode($results, JSON_UNESCAPED_SLASHES);

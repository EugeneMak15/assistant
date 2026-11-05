<?php
// Read-only exact-SKU article/KB export for targeted Advisor indexing.
$skus = ['BG-4K-VP1616PRO','BG-IPGEAR-PRO','BG-IPGEAR-PRO-T','BG-IPGEAR-PRO-R',
    'BG-UHD-VWP110L','BG-EXH-8K100U','BG-EXH-8K50C','BG-EXH-4KFE','BG-8KCH'];
global $wpdb;
$ids = [];
foreach ($skus as $sku) {
    $like = '%' . $wpdb->esc_like($sku) . '%';
    $ids = array_merge($ids, $wpdb->get_col($wpdb->prepare(
        "SELECT ID FROM {$wpdb->posts} WHERE post_status='publish' AND post_type IN ('post','knowledge_base','solution','case','faq_item') AND (post_title LIKE %s OR post_content LIKE %s) LIMIT 60",
        $like, $like)));
}
$out = [];
foreach (array_unique($ids) as $id) {
    $post = get_post($id);
    if (!$post) continue;
    $text = html_entity_decode(wp_strip_all_tags($post->post_content), ENT_QUOTES, 'UTF-8');
    $text = trim(preg_replace('/\s+/u', ' ', $text));
    if (mb_strlen($text) < 150) continue;
    $related = [];
    foreach ($skus as $sku) {
        $pattern = '/(?<![A-Za-z0-9_-])' . preg_quote($sku, '/') . '(?![A-Za-z0-9_-])/i';
        if (preg_match($pattern, $post->post_title . ' ' . $text)) $related[] = $sku;
    }
    if (!$related) continue;
    if (in_array('BG-IPGEAR-PRO', $related, true)) {
        $related = array_values(array_unique(array_merge($related, ['BG-IPGEAR-PRO-T','BG-IPGEAR-PRO-R'])));
    }
    $out[] = ['title' => get_the_title($id), 'url' => get_permalink($id),
        'doc_type' => $post->post_type, 'text' => mb_substr($text, 0, 20000), 'related_skus' => $related];
}
echo wp_json_encode($out, JSON_UNESCAPED_SLASHES);

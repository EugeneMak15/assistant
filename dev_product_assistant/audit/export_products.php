<?php
// Read-only WooCommerce catalog export for Advisor coverage audit.
$rows = [];
$ids = get_posts(['post_type' => 'product', 'post_status' => 'publish', 'posts_per_page' => -1, 'fields' => 'ids']);
foreach ($ids as $id) {
    $product = wc_get_product($id);
    if (!$product || !$product->is_visible()) continue;
    $resources = [];
    $groups = get_field('resources', $id);
    if (is_array($groups)) foreach ($groups as $group) foreach (($group['files'] ?? []) as $file) {
        $raw = ($file['type'] ?? '') === 'url' ? ($file['url'] ?? '') : ($file['file'] ?? '');
        $url = is_array($raw) ? ($raw['url'] ?? '') : (is_numeric($raw) ? wp_get_attachment_url((int)$raw) : $raw);
        if ($url) $resources[] = ['title' => wp_strip_all_tags((string)($file['name'] ?? '')), 'url' => $url];
    }
    $variants = [];
    if ($product->is_type('variable')) foreach ($product->get_children() as $child_id) {
        $child = wc_get_product($child_id);
        if ($child && $child->get_status() === 'publish') $variants[] = $child->get_sku();
    }
    $post = get_post($id);
    $rows[] = [
        'id' => $id,
        'sku' => $product->get_sku(),
        'title' => $product->get_name(),
        'url' => get_permalink($id),
        'date' => $post->post_date,
        'modified' => $post->post_modified,
        'type' => $product->get_type(),
        'stock' => $product->get_stock_status(),
        'visibility' => $product->get_catalog_visibility(),
        'lifecycle' => is_scalar(get_field('status', $id)) ? (string)get_field('status', $id) : '',
        'variants' => array_values(array_filter($variants)),
        'description_chars' => mb_strlen(wp_strip_all_tags($product->get_description())),
        'spec_chars' => mb_strlen(wp_strip_all_tags((string)get_post_meta($id, 'specifications', true))),
        'interface_chars' => mb_strlen(wp_strip_all_tags((string)get_post_meta($id, 'interfaces_description', true))),
        'resources' => $resources,
    ];
}
echo wp_json_encode($rows, JSON_UNESCAPED_SLASHES);

<?php
/**
 * Plugin Name: BZB Product AI (Dev)
 * Description: SKU-scoped product Q&A for dev.bzbgear.com only.
 * Version: 0.1.4
 */
defined('ABSPATH') || exit;
if (wp_parse_url(home_url(), PHP_URL_HOST) !== 'dev.bzbgear.com') return;

add_action('wp_enqueue_scripts', function () {
    if (!is_product()) return;
    $base = plugin_dir_url(__FILE__);
    wp_enqueue_style('bzb-product-ai-dev', $base . 'product-ai.css', [], '0.1.2');
    wp_enqueue_script('bzb-product-ai-dev', $base . 'product-ai.js', [], '0.1.2', true);
    wp_localize_script('bzb-product-ai-dev', 'bzbProductAI', [
        'api' => esc_url_raw(admin_url('admin-ajax.php')),
        'nonce' => wp_create_nonce('wp_rest'),
        'productId' => get_queried_object_id(),
    ]);
});

add_action('wp_footer', function () {
    if (!is_product()) return;
    $product = wc_get_product(get_queried_object_id());
    if (!$product) return;
    ?>
    <button type="button" class="bzb-product-ai-button" data-bzb-product-ai-open aria-haspopup="dialog" aria-controls="bzb-product-ai-panel">
      <span class="bzb-product-ai-button__spark" aria-hidden="true">✦</span> Ask AI about this product
    </button>
    <div class="bzb-product-ai-layer" hidden>
      <div class="bzb-product-ai-backdrop" data-bzb-product-ai-close></div>
      <section class="bzb-product-ai-panel" id="bzb-product-ai-panel" role="dialog" aria-modal="true" aria-labelledby="bzb-product-ai-title" tabindex="-1">
        <header class="bzb-product-ai-header">
          <div><span class="bzb-product-ai-eyebrow">PRODUCT ASSISTANT</span><strong id="bzb-product-ai-title"><?php echo esc_html($product->get_name()); ?></strong><small><?php echo esc_html($product->get_sku()); ?></small></div>
          <button type="button" class="bzb-product-ai-close" data-bzb-product-ai-close aria-label="Close product assistant">×</button>
        </header>
        <div class="bzb-product-ai-messages" role="log" aria-live="polite"></div>
        <div class="bzb-product-ai-suggestions">
          <button type="button" data-bzb-question="What are the key specifications?">Specifications</button>
          <button type="button" data-bzb-question="How do I connect this product?">Connections</button>
          <button type="button" data-bzb-question="Where can I find the manual and diagram?">Manual &amp; diagram</button>
        </div>
        <form class="bzb-product-ai-form">
          <label class="screen-reader-text" for="bzb-product-ai-input">Ask about this product</label>
          <input id="bzb-product-ai-input" maxlength="1200" autocomplete="off" placeholder="Ask about specs, setup, compatibility…" required>
          <button type="submit" aria-label="Send question">↑</button>
        </form>
        <div class="bzb-product-ai-note">Answers are based on available product materials. Verify critical requirements in the manual.</div>
      </section>
    </div>
    <?php
}, 6);

function bzb_product_ai_plain($value, $limit = 12000) {
    if (!is_string($value)) return '';
    return mb_substr(trim(preg_replace('/\s+/u', ' ', html_entity_decode(wp_strip_all_tags($value), ENT_QUOTES, 'UTF-8'))), 0, $limit);
}

function bzb_product_ai_context($id) {
    $product = wc_get_product($id);
    if (!$product || $product->get_status() !== 'publish' || !$product->is_visible()) return null;
    $sections = [
        'Description' => bzb_product_ai_plain($product->get_description()),
        'Short description' => bzb_product_ai_plain($product->get_short_description()),
        'Specifications' => bzb_product_ai_plain(get_post_meta($id, 'specifications', true)),
        'Interfaces' => bzb_product_ai_plain(get_post_meta($id, 'interfaces_description', true)),
        'Additional interfaces' => bzb_product_ai_plain(get_post_meta($id, 'interfaces_2_description', true)),
        'Package contents' => bzb_product_ai_plain(get_post_meta($id, 'package_contents', true)),
    ];
    $attributes = [];
    foreach ($product->get_attributes() as $attribute) {
        if ($attribute->is_taxonomy()) {
            $values = wc_get_product_terms($id, $attribute->get_name(), ['fields' => 'names']);
        } else {
            $values = $attribute->get_options();
        }
        $attributes[wc_attribute_label($attribute->get_name())] = implode(', ', array_map('strval', $values));
    }
    $sections['Attributes'] = bzb_product_ai_plain(wp_json_encode($attributes));
    $variant_skus = [];
    if ($product->is_type('variable')) {
        $variants = [];
        foreach (array_slice($product->get_children(), 0, 300) as $child_id) {
            $child = wc_get_product($child_id);
            if (!$child || $child->get_status() !== 'publish') continue;
            if ($child->get_sku()) $variant_skus[] = $child->get_sku();
            $variants[] = [
                'sku' => $child->get_sku(),
                'name' => $child->get_name(),
                'attributes' => $child->get_variation_attributes(),
                'description' => bzb_product_ai_plain($child->get_description(), 1000),
            ];
        }
        $sections['Variations'] = bzb_product_ai_plain(wp_json_encode($variants), 60000);
    }
    $resources = [];
    $groups = get_field('resources', $id);
    if (is_array($groups)) foreach ($groups as $group) {
        foreach (($group['files'] ?? []) as $file) {
            $raw = ($file['type'] ?? '') === 'url' ? ($file['url'] ?? '') : ($file['file'] ?? '');
            $url = is_array($raw) ? ($raw['url'] ?? '') : (is_numeric($raw) ? wp_get_attachment_url((int) $raw) : $raw);
            if (!$url || !wp_http_validate_url($url)) continue;
            if (preg_match('/\b(spanish|espa[nñ]ol|french|german|portuguese|italian|russian|chinese|japanese|korean)\b/i', ($file['name'] ?? '') . ' ' . $url)) continue;
            if (preg_match('/(?:^|[\/_.-])(es|es-mx|fr|de|pt|it|ru|zh|ja|ko)(?:[\/_.-]|$)/i', wp_parse_url($url, PHP_URL_PATH))) continue;
            $resources[] = ['title' => bzb_product_ai_plain($file['name'] ?? 'Product document', 160), 'url' => esc_url_raw($url)];
        }
    }
    return [
        'sku' => $product->get_sku() ?: ('product-' . $id),
        'name' => $product->get_name(),
        'product_url' => get_permalink($id),
        'sections' => array_filter($sections),
        'variant_skus' => $variant_skus,
        'resources' => array_slice($resources, 0, 30),
        'articles' => bzb_product_ai_articles(array_merge([$product->get_sku()], $variant_skus)),
    ];
}

function bzb_product_ai_articles($skus) {
    $skus = array_values(array_filter($skus));
    if (!$skus) return [];
    $key = 'bzb_product_ai_articles_v2_' . md5(implode('|', $skus));
    $cached = get_transient($key);
    if (is_array($cached)) return $cached;
    global $wpdb;
    $ids = [];
    foreach (array_slice($skus, 0, 30) as $sku) {
        $like = '%' . $wpdb->esc_like($sku) . '%';
        $ids = array_merge($ids, $wpdb->get_col($wpdb->prepare(
            "SELECT ID FROM {$wpdb->posts} WHERE post_status='publish' AND post_type IN ('post','knowledge_base','solution','case','faq_item') AND (post_title LIKE %s OR post_content LIKE %s) LIMIT 30",
            $like, $like
        )));
    }
    $articles = [];
    $pattern = '/(?<![A-Za-z0-9_-])(?:' . implode('|', array_map(function ($sku) { return preg_quote($sku, '/'); }, $skus)) . ')(?![A-Za-z0-9_-])/i';
    foreach (array_unique($ids) as $id) {
        $post = get_post($id);
        if (!$post || !is_post_type_viewable($post->post_type)) continue;
        $text = bzb_product_ai_plain($post->post_content, 30000);
        if (!preg_match($pattern, $post->post_title . ' ' . $text)) continue;
        preg_match($pattern, $text, $match, PREG_OFFSET_CAPTURE);
        $position = empty($match) ? false : mb_strlen(substr($text, 0, $match[0][1]));
        $excerpt = $position === false ? mb_substr($text, 0, 2500) : mb_substr($text, max(0, $position - 600), 3000);
        $articles[] = ['title' => get_the_title($id), 'url' => get_permalink($id), 'text' => $excerpt];
        if (count($articles) >= 8) break;
    }
    set_transient($key, $articles, DAY_IN_SECONDS);
    return $articles;
}

function bzb_product_ai_answer(WP_REST_Request $request) {
            $id = absint($request->get_param('product_id'));
            $question = trim((string) $request->get_param('question'));
            if (!$id || $question === '' || mb_strlen($question) > 1200) return new WP_Error('bad_request', 'Invalid question.', ['status' => 400]);
            $nonce = $request->get_header('X-WP-Nonce');
            if (!wp_verify_nonce($nonce, 'wp_rest')) return new WP_Error('bad_nonce', 'Refresh the product page and try again.', ['status' => 403]);
            $context = bzb_product_ai_context($id);
            if (!$context) return new WP_Error('not_found', 'Product not found.', ['status' => 404]);
            $ip = sanitize_text_field($_SERVER['REMOTE_ADDR'] ?? 'unknown');
            $key = 'bzb_product_ai_' . md5(gmdate('Y-m-d') . '|' . $ip);
            $count = (int) get_transient($key);
            if ($count >= 50) return new WP_Error('rate_limit', 'Daily test limit reached. Please try tomorrow.', ['status' => 429]);
            set_transient($key, $count + 1, DAY_IN_SECONDS);
            $history = $request->get_param('history');
            $context['question'] = $question;
            $context['history'] = is_array($history) ? array_slice($history, -8) : [];
            // Dev migration preview blocks wp_remote_post globally. This fixed loopback
            // call never follows redirects or accepts a user-supplied destination.
            $curl = curl_init('http://127.0.0.1:8002/ask');
            curl_setopt_array($curl, [
                CURLOPT_POST => true,
                CURLOPT_POSTFIELDS => wp_json_encode($context),
                CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_TIMEOUT => 45,
                CURLOPT_FOLLOWLOCATION => false,
                CURLOPT_PROXY => '',
            ]);
            $raw = curl_exec($curl);
            $status = curl_getinfo($curl, CURLINFO_HTTP_CODE);
            curl_close($curl);
            if ($status === 429) return new WP_Error('busy', 'Product assistant is busy. Please try again shortly.', ['status' => 429]);
            if ($raw === false || $status !== 200) {
                return new WP_Error('unavailable', 'Product assistant is temporarily unavailable.', ['status' => 503]);
            }
            $body = json_decode($raw, true);
            if (!is_array($body) || empty($body['answer'])) return new WP_Error('empty_answer', 'Could not get an answer.', ['status' => 502]);
            return ['answer' => $body['answer'], 'sources' => $body['sources'] ?? []];
}

add_action('rest_api_init', function () {
    register_rest_route('bzb-product-ai/v1', '/ask', [
        'methods' => 'POST',
        'permission_callback' => '__return_true',
        'callback' => 'bzb_product_ai_answer',
    ]);
});

function bzb_product_ai_ajax() {
    $request = new WP_REST_Request('POST', '/bzb-product-ai/v1/ask');
    $request->set_header('X-WP-Nonce', sanitize_text_field(wp_unslash($_POST['nonce'] ?? '')));
    $request->set_body_params([
        'product_id' => absint($_POST['product_id'] ?? 0),
        'question' => sanitize_text_field(wp_unslash($_POST['question'] ?? '')),
        'history' => json_decode(wp_unslash($_POST['history'] ?? '[]'), true),
    ]);
    $result = bzb_product_ai_answer($request);
    if (is_wp_error($result)) wp_send_json(['message' => $result->get_error_message()], $result->get_error_data()['status'] ?? 500);
    wp_send_json($result);
}
add_action('wp_ajax_bzb_product_ai_ask', 'bzb_product_ai_ajax');
add_action('wp_ajax_nopriv_bzb_product_ai_ask', 'bzb_product_ai_ajax');

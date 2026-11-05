<?php
// Exercise the same handler used by the browser without the Dev Basic Auth wall.
$_POST = [
    'nonce' => wp_create_nonce('wp_rest'),
    'product_id' => '126837',
    'question' => 'What does the EDID dial do?',
    'history' => '[]',
];
bzb_product_ai_ajax();

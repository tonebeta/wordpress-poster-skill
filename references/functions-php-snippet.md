# WordPress functions.php SEO Snippet

將以下程式碼加入你的 WordPress 主題的 `functions.php`（或 child theme），
讓 Yoast SEO 及 Rank Math 的 meta 欄位可透過 REST API 寫入。

**不加這段的話**：呼叫 API 寫入 meta 可能被 WordPress 忽略（欄位未註冊為 REST 可寫）。

---

## 加入方式

**WP Admin → Appearance → Theme File Editor → functions.php**

或透過 SSH：
```bash
nano /var/www/html/wp-content/themes/your-theme/functions.php
```

---

## Snippet（Yoast SEO）

```php
<?php
/**
 * 讓 Yoast SEO meta 欄位可透過 WordPress REST API 讀寫
 * 加入 functions.php 或 child theme 的 functions.php
 */
add_action( 'init', function () {
    $yoast_fields = [
        '_yoast_wpseo_title'               => 'SEO title',
        '_yoast_wpseo_metadesc'            => 'Meta description',
        '_yoast_wpseo_focuskw'             => 'Focus keyword',
        '_yoast_wpseo_canonical'           => 'Canonical URL',
        '_yoast_wpseo_opengraph-title'     => 'OG title',
        '_yoast_wpseo_opengraph-description' => 'OG description',
        '_yoast_wpseo_meta-robots-noindex' => 'No-index flag',
    ];

    foreach ( [ 'post', 'page' ] as $post_type ) {
        foreach ( $yoast_fields as $meta_key => $description ) {
            register_post_meta( $post_type, $meta_key, [
                'show_in_rest'      => true,
                'single'            => true,
                'type'              => 'string',
                'auth_callback'     => function () {
                    return current_user_can( 'edit_posts' );
                },
            ] );
        }
    }
} );
```

---

## Snippet（Rank Math）

```php
<?php
/**
 * 讓 Rank Math SEO meta 欄位可透過 WordPress REST API 讀寫
 */
add_action( 'init', function () {
    $rankmath_fields = [
        'rank_math_title'                => 'SEO title',
        'rank_math_description'          => 'Meta description',
        'rank_math_focus_keyword'        => 'Focus keyword',
        'rank_math_canonical_url'        => 'Canonical URL',
        'rank_math_facebook_title'       => 'Facebook OG title',
        'rank_math_facebook_description' => 'Facebook OG description',
    ];

    foreach ( [ 'post', 'page' ] as $post_type ) {
        foreach ( $rankmath_fields as $meta_key => $description ) {
            register_post_meta( $post_type, $meta_key, [
                'show_in_rest'  => true,
                'single'        => true,
                'type'          => 'string',
                'auth_callback' => function () {
                    return current_user_can( 'edit_posts' );
                },
            ] );
        }
    }
} );
```

---

## 驗證是否生效

加入後，執行以下指令確認欄位可寫：

```bash
# 確認 meta schema 包含 SEO 欄位
curl -s https://your-site.com/wp-json/wp/v2/posts \
  -u "username:app_password" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(list(d[0].get('meta',{}).keys()))"
```

應該看到 `_yoast_wpseo_title` 或 `rank_math_title` 等欄位出現在輸出中。

---

## 注意事項

- 修改 `functions.php` 前請先備份
- 若使用 child theme，優先加入 child theme 的 `functions.php`
- 更改後不需重啟，立即生效
- Yoast SEO 燈號（紅/橙/綠）仍需在 WP admin 手動開啟文章並儲存一次才會更新
  （這是 Yoast indexable 系統的已知限制，不影響實際 SEO meta 輸出）

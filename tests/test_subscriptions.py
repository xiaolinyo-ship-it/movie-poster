import unittest

from app.subscriptions import (
    SubscriptionLoginRequired,
    parse_recent_updates,
    titles_match,
)


class SubscriptionParserTests(unittest.TestCase):
    def test_extracts_recent_updates_only(self):
        html = """
        <h2>最近更新的影视</h2>
        <table>
          <tr><th>序号</th><th>名称</th><th>更新时间</th><th>链接</th></tr>
          <tr><td>1</td><td>人生复本 第二季</td><td>11 小时前</td><td><a href="/x/1">查看</a></td></tr>
          <tr><td>2</td><td>百年孤独 第二季</td><td>2026-08-30</td><td><a href="/x/2">查看</a></td></tr>
        </table>
        """
        items = parse_recent_updates(html)
        self.assertEqual([item.title for item in items], ["人生复本 第二季", "百年孤独 第二季"])
        self.assertEqual(items[0].url, "/x/1")

    def test_login_page_fails_closed(self):
        with self.assertRaises(SubscriptionLoginRequired):
            parse_recent_updates('<form><input name="password" type="password"></form>')

    def test_matches_local_title_without_season_suffix(self):
        self.assertTrue(titles_match("人生复本", "人生复本 第二季"))
        self.assertFalse(titles_match("星城", "星际迷航"))


if __name__ == "__main__":
    unittest.main()

"""草稿失败分诊：这次失败之后能不能安全重跑？

这组测试锁的是一个真踩到过的坑：40164（IP 不在白名单）曾被判成
`outcome=uncertain / retry_safe=false`，于是加白之后 finish 拒绝继续，必须
人工把 draft 阶段重置为 pending 才能重跑——而那次失败其实发生在拿
access_token 阶段，draft/add 根本没发出去，远端不可能有草稿。

判据是结构性的，不是错误码枚举：**只有 draft/add 这个写请求发出后读不到响应，
远端状态才不可知。** 其余所有失败路径都可以安全重跑。
"""

import importlib.util
import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNTIME = os.path.join(
    ROOT, ".agents", "skills", "wechat-content-pipeline", "scripts",
    "pipeline_runtime.py",
)
PUBLISH = os.path.join(ROOT, "scripts", "wechat_publish.py")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = load_module("pipeline_runtime_for_triage", RUNTIME)
publish = load_module("wechat_publish_for_triage", PUBLISH)


class DraftRetrySafetyTests(unittest.TestCase):
    def test_server_rejected_errors_are_retry_safe(self):
        """服务端明确回了 errcode = 明确拒绝，草稿一定没建。"""
        for errcode, label in (
            (40164, "IP 不在白名单"),
            (40001, "AppSecret 错误"),
            (48001, "接口未授权"),
            (45009, "调用频次超限"),
        ):
            with self.subTest(errcode=errcode, label=label):
                message = (
                    f"✗ 微信 API 错误 {errcode}: some errmsg\n"
                    "draft_may_exist=false"
                )
                self.assertTrue(runtime.draft_failure_is_retry_safe(message))

    def test_draft_add_transport_failure_is_not_retry_safe(self):
        """draft/add 已发出但没读到响应：远端可能已有草稿，禁止自动重发。"""
        message = (
            "✗ 微信 API 请求失败：<urlopen error [Errno 54] Connection reset by peer>\n"
            "draft_may_exist=true"
        )
        self.assertFalse(runtime.draft_failure_is_retry_safe(message))

    def test_legacy_message_without_marker_still_recognised(self):
        """发布器若是不带标记的旧版本，本地配置错误仍应判为可重跑。"""
        for message in (
            "✗ 未设置 AppID 环境变量：WECHAT_A_APP_ID",
            "✗ 配置中没有账号 'z'；可用账号：a, b",
            "✗ 账号 'a' 缺少 appid_env",
        ):
            with self.subTest(message=message):
                self.assertTrue(runtime.draft_failure_is_retry_safe(message))

    def test_unknown_failure_defaults_to_unsafe(self):
        """既没标记也不匹配旧模式时保守判定，宁可让人核对也不要造双草稿。"""
        self.assertFalse(runtime.draft_failure_is_retry_safe("✗ 某个陌生错误"))
        self.assertFalse(runtime.draft_failure_is_retry_safe(""))


class PublishErrorContractTests(unittest.TestCase):
    def test_draft_may_exist_defaults_to_false(self):
        self.assertFalse(publish.PublishError("boom").draft_may_exist)

    def test_draft_may_exist_can_be_set(self):
        self.assertTrue(
            publish.PublishError("boom", draft_may_exist=True).draft_may_exist
        )

    def test_40164_remediation_names_the_right_ip_source(self):
        """40164 的提示必须挡住 `curl ifconfig.me` 这个错误做法。

        本仓库的发布器强制直连 api.weixin.qq.com（忽略 HTTP(S)_PROXY），而 curl
        走本机代理；有分流规则时两者出口不同，加白 curl 给的 IP 不会生效。
        """
        hint = publish.errcode_remediation(40164)
        self.assertIn("白名单", hint)
        self.assertIn("ifconfig.me", hint)
        self.assertIn("直连", hint)

    def test_remediation_is_empty_for_unknown_errcode(self):
        self.assertEqual(publish.errcode_remediation(999999), "")


if __name__ == "__main__":
    unittest.main()

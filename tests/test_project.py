import unittest

from project import calculate, invoke, parse_action, run, sensor_summary


class DemoClient:
    enabled = False


class RepeatingClient:
    enabled = True

    def complete(self, *args, **kwargs):
        return '{"tool":"sensor_summary","arguments":{"equipment":"P-101"}}'


class ToolAgentTests(unittest.TestCase):
    def test_arithmetic_precedence(self):
        self.assertEqual(calculate("2 + 3 * (4 - 1)")["value"], 11)

    def test_code_is_rejected(self):
        for expression in ["__import__('os')", "2 ** 100", "True", "1 / 0"]:
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                calculate(expression)

    def test_tool_allowlist_and_arguments(self):
        with self.assertRaises(ValueError):
            invoke("shell", {"command": "anything"})
        with self.assertRaises(ValueError):
            invoke("sensor_summary", {"window": True})
        with self.assertRaises(ValueError):
            invoke("calculate", {"expression": "1", "extra": "no"})

    def test_actual_sensor_mean(self):
        self.assertEqual(sensor_summary(window=5)["mean"], 75)

    def test_demo_combines_tools(self):
        result = run({"text": "P-101 最近5次温度与阈值70比较"}, DemoClient())
        self.assertEqual(result["metrics"]["工具调用"], 2)
        self.assertIn("5.0", result["summary"])

    def test_repeat_protection(self):
        result = run({"text": "分析P-101"}, RepeatingClient())
        self.assertEqual(result["metrics"]["执行状态"], "repeat_stopped")
        self.assertEqual(result["metrics"]["工具调用"], 1)

    def test_unknown_device_is_reported(self):
        result = run({"text": "P-999 最近5次温度"}, DemoClient())
        self.assertEqual(result["metrics"]["执行状态"], "tool_error")
        self.assertIn("没有这个设备", result["summary"])

    def test_unrelated_task_is_not_fabricated(self):
        with self.assertRaises(ValueError):
            run({"text": "写一首诗"}, DemoClient())

    def test_empty_input(self):
        with self.assertRaises(ValueError):
            run({"text": " "}, DemoClient())


if __name__ == "__main__":
    unittest.main()

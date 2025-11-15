"""
测试AstrBot代码审查器
"""

from astrbot_code_auditor import AstrBotCodeAuditor


# 测试代码1: 一个基本符合规范的插件
good_code = """
from astrbot.api import logger
from astrbot.api.star import Star, Context
from astrbot.api.event import filter, AstrMessageEvent

class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    @filter.command("test")
    async def test(self, event: AstrMessageEvent):
        '''测试指令'''
        logger.info("测试指令被调用")
        yield event.plain_result("Hello!")
"""

# 测试代码2: 违反多项规范的插件
bad_code = """
import logging
import requests
from astrbot.api.star import Star, Context

class MyPlugin(Star):
    def __init__(self, context):
        super().__init__(context)
    
    def test(self, event):
        logging.info("测试")
        response = requests.get("https://example.com")
        return "Hello!"
"""


def test_good_code():
    """测试符合规范的代码"""
    print("=" * 80)
    print("测试1: 符合规范的代码")
    print("=" * 80)
    
    auditor = AstrBotCodeAuditor()
    result = auditor.audit_code(good_code, "main.py")
    
    print(f"\n✅ 审查通过: {result['approved']}")
    print(f"📊 满意度分数: {result['satisfaction_score']}/100")
    print(f"📝 Pylint评分: {result['pylint_score']:.1f}/10")
    print(f"\n检查结果:")
    print(f"  - Ruff: {'✓ 通过' if result['ruff_passed'] else '✗ 未通过'}")
    print(f"  - Pylint: {'✓ 通过' if result['pylint_passed'] else '✗ 未通过'}")
    print(f"  - Mypy: {'✓ 通过' if result['mypy_passed'] else '✗ 未通过'}")
    print(f"  - AstrBot规则: {'✓ 通过' if result['astrbot_rules_passed'] else '✗ 未通过'}")
    
    if result['issues']:
        print(f"\n⚠️  发现 {len(result['issues'])} 个问题:")
        for i, issue in enumerate(result['issues'][:10], 1):
            print(f"  {i}. {issue}")
        if len(result['issues']) > 10:
            print(f"  ... 还有 {len(result['issues']) - 10} 个问题")
    else:
        print("\n✨ 未发现任何问题!")
    
    print(f"\n💡 审查理由: {result['reason']}")
    print()


def test_bad_code():
    """测试违反规范的代码"""
    print("=" * 80)
    print("测试2: 违反规范的代码")
    print("=" * 80)
    
    auditor = AstrBotCodeAuditor()
    result = auditor.audit_code(bad_code, "main.py")
    
    print(f"\n❌ 审查通过: {result['approved']}")
    print(f"📊 满意度分数: {result['satisfaction_score']}/100")
    print(f"📝 Pylint评分: {result['pylint_score']:.1f}/10")
    print(f"\n检查结果:")
    print(f"  - Ruff: {'✓ 通过' if result['ruff_passed'] else '✗ 未通过'}")
    print(f"  - Pylint: {'✓ 通过' if result['pylint_passed'] else '✗ 未通过'}")
    print(f"  - Mypy: {'✓ 通过' if result['mypy_passed'] else '✗ 未通过'}")
    print(f"  - AstrBot规则: {'✓ 通过' if result['astrbot_rules_passed'] else '✗ 未通过'}")
    
    if result['issues']:
        print(f"\n⚠️  发现 {len(result['issues'])} 个问题:")
        for i, issue in enumerate(result['issues'][:15], 1):
            print(f"  {i}. {issue}")
        if len(result['issues']) > 15:
            print(f"  ... 还有 {len(result['issues']) - 15} 个问题")
    
    print(f"\n💡 审查理由: {result['reason']}")
    print()


if __name__ == "__main__":
    print("\n🔍 AstrBot代码审查器测试\n")
    
    # 测试符合规范的代码
    test_good_code()
    
    # 测试违反规范的代码
    test_bad_code()
    
    print("=" * 80)
    print("测试完成!")
    print("=" * 80)

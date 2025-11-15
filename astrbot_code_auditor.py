"""
AstrBot代码审查器
使用ruff、pylint和mypy对LLM生成的AstrBot插件代码进行静态分析
"""

import os
import re
import json
import tempfile
import subprocess
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from astrbot.api import logger


class AstrBotCodeAuditor:
    """AstrBot插件代码审查器"""
    
    def __init__(self, project_root: Optional[str] = None):
        """初始化审查器
        
        Args:
            project_root: 项目根目录，如果为None则使用当前文件所在目录
        """
        self.project_root = project_root or os.path.dirname(os.path.abspath(__file__))
        self.ruff_config = self._get_ruff_config_path()
        self.pylint_config = self._get_pylint_config_path()
        self.mypy_config = self._get_mypy_config_path()
        
    def _get_ruff_config_path(self) -> str:
        """获取ruff配置文件路径"""
        return os.path.join(self.project_root, ".ruff.toml")
    
    def _get_pylint_config_path(self) -> str:
        """获取pylint配置文件路径"""
        return os.path.join(self.project_root, ".pylintrc")
    
    def _get_mypy_config_path(self) -> str:
        """获取mypy配置文件路径"""
        return os.path.join(self.project_root, "mypy.ini")
    
    def _check_tool_installed(self, tool: str) -> bool:
        """检查工具是否已安装
        
        Args:
            tool: 工具名称
            
        Returns:
            bool: 是否已安装
        """
        try:
            result = subprocess.run(
                [tool, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _run_ruff(self, file_path: str) -> Tuple[bool, List[str]]:
        """运行ruff检查
        
        Args:
            file_path: 要检查的文件路径
            
        Returns:
            Tuple[bool, List[str]]: (是否通过, 问题列表)
        """
        if not self._check_tool_installed("ruff"):
            logger.warning("ruff未安装，跳过ruff检查")
            return True, []
        
        issues = []
        try:
            # 运行ruff check
            cmd = ["ruff", "check", file_path]
            if os.path.exists(self.ruff_config):
                cmd.extend(["--config", self.ruff_config])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.stdout:
                # 解析ruff输出
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        issues.append(f"[Ruff] {line}")
            
            # 运行ruff format检查
            format_result = subprocess.run(
                ["ruff", "format", "--check", file_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if format_result.returncode != 0:
                issues.append("[Ruff] 代码格式不符合规范，建议运行 ruff format 进行格式化")
            
            return len(issues) == 0, issues
            
        except subprocess.TimeoutExpired:
            logger.error("ruff检查超时")
            return False, ["[Ruff] 检查超时"]
        except Exception as e:
            logger.error(f"ruff检查失败: {str(e)}")
            return False, [f"[Ruff] 检查失败: {str(e)}"]
    
    def _run_pylint(self, file_path: str) -> Tuple[bool, List[str], float]:
        """运行pylint检查
        
        Args:
            file_path: 要检查的文件路径
            
        Returns:
            Tuple[bool, List[str], float]: (是否通过, 问题列表, 评分)
        """
        if not self._check_tool_installed("pylint"):
            logger.warning("pylint未安装，跳过pylint检查")
            return True, [], 10.0
        
        issues = []
        score = 10.0
        
        try:
            cmd = ["pylint", file_path, "--output-format=json"]
            if os.path.exists(self.pylint_config):
                cmd.append(f"--rcfile={self.pylint_config}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            # 解析JSON输出
            if result.stdout:
                try:
                    pylint_results = json.loads(result.stdout)
                    for item in pylint_results:
                        msg_type = item.get('type', 'unknown')
                        message = item.get('message', '')
                        line = item.get('line', 0)
                        symbol = item.get('symbol', '')
                        issues.append(
                            f"[Pylint:{msg_type}] Line {line}: {message} ({symbol})"
                        )
                except json.JSONDecodeError:
                    pass
            
            # 提取评分
            if result.stderr:
                score_match = re.search(r'Your code has been rated at ([\d.]+)/10', result.stderr)
                if score_match:
                    score = float(score_match.group(1))
            
            # pylint评分低于7.0认为不通过
            passed = score >= 7.0 and len([i for i in issues if '[Pylint:error]' in i or '[Pylint:fatal]' in i]) == 0
            
            return passed, issues, score
            
        except subprocess.TimeoutExpired:
            logger.error("pylint检查超时")
            return False, ["[Pylint] 检查超时"], 0.0
        except Exception as e:
            logger.error(f"pylint检查失败: {str(e)}")
            return False, [f"[Pylint] 检查失败: {str(e)}"], 0.0
    
    def _run_mypy(self, file_path: str) -> Tuple[bool, List[str]]:
        """运行mypy类型检查
        
        Args:
            file_path: 要检查的文件路径
            
        Returns:
            Tuple[bool, List[str]]: (是否通过, 问题列表)
        """
        if not self._check_tool_installed("mypy"):
            logger.warning("mypy未安装，跳过mypy检查")
            return True, []
        
        issues = []
        
        try:
            cmd = ["mypy", file_path]
            if os.path.exists(self.mypy_config):
                cmd.append(f"--config-file={self.mypy_config}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.stdout:
                # 解析mypy输出
                for line in result.stdout.strip().split('\n'):
                    if line.strip() and ':' in line:
                        # 过滤掉"Found X errors"这类总结信息
                        if not line.startswith('Found') and not line.startswith('Success'):
                            issues.append(f"[Mypy] {line}")
            
            # mypy有error认为不通过
            has_errors = any('error:' in issue.lower() for issue in issues)
            
            return not has_errors, issues
            
        except subprocess.TimeoutExpired:
            logger.error("mypy检查超时")
            return False, ["[Mypy] 检查超时"]
        except Exception as e:
            logger.error(f"mypy检查失败: {str(e)}")
            return False, [f"[Mypy] 检查失败: {str(e)}"]
    
    def _check_astrbot_specific_rules(self, code: str, file_path: str) -> Tuple[bool, List[str]]:
        """检查AstrBot特定规则
        
        Args:
            code: 源代码内容
            file_path: 文件路径
            
        Returns:
            Tuple[bool, List[str]]: (是否通过, 问题列表)
        """
        issues = []
        
        # 检查是否使用了禁用的logging模块
        if re.search(r'import\s+logging|from\s+logging\s+import', code):
            issues.append("[AstrBot规则] 禁止使用logging模块，请使用 from astrbot.api import logger")
        
        # 检查是否使用了requests库（应该使用异步库）
        if re.search(r'import\s+requests|from\s+requests\s+import', code):
            issues.append("[AstrBot规则] 不建议使用requests库，请使用aiohttp或httpx等异步库")
        
        # 检查filter导入是否正确
        if '@filter.' in code:
            if not re.search(r'from\s+astrbot\.api\.event\s+import.*filter', code):
                issues.append("[AstrBot规则] 使用@filter装饰器时必须从astrbot.api.event导入filter")
        
        # 如果是main.py，进行额外检查
        if file_path.endswith('main.py'):
            # 检查是否继承Star类
            if not re.search(r'class\s+\w+\(Star\):', code):
                issues.append("[AstrBot规则] main.py中必须有一个继承自Star的插件类")
            
            # 检查__init__方法签名
            init_pattern = r'def\s+__init__\(self,\s*context:\s*Context(?:,\s*config:\s*AstrBotConfig)?\)'
            if 'def __init__' in code and not re.search(init_pattern, code):
                issues.append("[AstrBot规则] 插件类__init__方法签名不正确，应为 def __init__(self, context: Context) 或 def __init__(self, context: Context, config: AstrBotConfig)")
        
        # 检查事件处理器签名（除了on_astrbot_loaded）
        event_decorators = [
            r'@filter\.command\(',
            r'@filter\.event_message_type\(',
            r'@filter\.on_llm_request\(',
            r'@filter\.on_llm_response\(',
            r'@filter\.on_decorating_result\(',
            r'@filter\.after_message_sent\(',
            r'@filter\.llm_tool\('
        ]
        
        for decorator_pattern in event_decorators:
            matches = list(re.finditer(decorator_pattern, code))
            for match in matches:
                # 获取装饰器后的函数定义
                start_pos = match.end()
                func_match = re.search(r'async\s+def\s+(\w+)\(([^)]*)\)', code[start_pos:start_pos+200])
                if func_match:
                    func_name = func_match.group(1)
                    params = func_match.group(2)
                    
                    # on_llm_request和on_llm_response需要3个参数
                    if 'on_llm_request' in decorator_pattern or 'on_llm_response' in decorator_pattern:
                        param_count = len([p for p in params.split(',') if p.strip()])
                        if param_count != 3:
                            issues.append(f"[AstrBot规则] {func_name}方法必须接收3个参数: self, event, 以及特定对象")
                    # 其他装饰器必须有event参数
                    elif 'event' not in params and func_name != 'on_astrbot_loaded':
                        issues.append(f"[AstrBot规则] {func_name}方法缺少event参数")
        
        # 检查是否在特殊钩子中使用了yield
        special_hooks = ['on_llm_request', 'on_llm_response', 'on_decorating_result', 'after_message_sent']
        for hook in special_hooks:
            # 查找这些钩子函数
            hook_pattern = rf'async\s+def\s+{hook}\([^)]*\):(.*?)(?=\n(?:async\s+def|\s*$|\nclass))'
            hook_matches = re.finditer(hook_pattern, code, re.DOTALL)
            for hook_match in hook_matches:
                hook_body = hook_match.group(1)
                if 'yield' in hook_body:
                    issues.append(f"[AstrBot规则] {hook}钩子中禁止使用yield，请使用event.send()方法")
        
        # 检查数据持久化路径
        if re.search(r'open\(["\'](?!.*StarTools\.get_data_dir)', code):
            # 查找硬编码的文件路径
            hardcoded_paths = re.findall(r'open\(["\']([^"\']+)["\']', code)
            for path in hardcoded_paths:
                # 排除明显的临时文件或配置文件
                if not any(x in path.lower() for x in ['tmp', 'temp', '/dev/', 'stdout', 'stderr']):
                    if '/' in path or '\\' in path:
                        issues.append(f"[AstrBot规则] 检测到硬编码路径 '{path}'，建议使用 StarTools.get_data_dir() 获取数据目录")
        
        return len(issues) == 0, issues
    
    def audit_code(self, code: str, file_name: str = "main.py") -> Dict[str, Any]:
        """审查代码
        
        Args:
            code: 源代码内容
            file_name: 文件名
            
        Returns:
            Dict[str, Any]: 审查结果
        """
        # 创建临时文件
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_file = f.name
        
        try:
            all_issues = []
            all_passed = True
            pylint_score = 10.0
            
            # 运行ruff检查
            logger.info("运行ruff检查...")
            ruff_passed, ruff_issues = self._run_ruff(temp_file)
            all_issues.extend(ruff_issues)
            all_passed = all_passed and ruff_passed
            
            # 运行pylint检查
            logger.info("运行pylint检查...")
            pylint_passed, pylint_issues, pylint_score = self._run_pylint(temp_file)
            all_issues.extend(pylint_issues)
            all_passed = all_passed and pylint_passed
            
            # 运行mypy检查
            logger.info("运行mypy类型检查...")
            mypy_passed, mypy_issues = self._run_mypy(temp_file)
            all_issues.extend(mypy_issues)
            all_passed = all_passed and mypy_passed
            
            # 运行AstrBot特定规则检查
            logger.info("运行AstrBot特定规则检查...")
            astrbot_passed, astrbot_issues = self._check_astrbot_specific_rules(code, file_name)
            all_issues.extend(astrbot_issues)
            all_passed = all_passed and astrbot_passed
            
            # 计算总体满意度分数
            # ruff和mypy是二元的（通过/不通过），pylint有评分
            # 总分 = pylint分数(0-10) * 10 = 0-100
            # 如果ruff或mypy不通过，扣20分
            satisfaction_score = int(pylint_score * 10)
            if not ruff_passed:
                satisfaction_score -= 20
            if not mypy_passed:
                satisfaction_score -= 20
            if not astrbot_passed:
                satisfaction_score -= 15
            satisfaction_score = max(0, min(100, satisfaction_score))
            
            result = {
                "approved": all_passed,
                "satisfaction_score": satisfaction_score,
                "pylint_score": pylint_score,
                "ruff_passed": ruff_passed,
                "pylint_passed": pylint_passed,
                "mypy_passed": mypy_passed,
                "astrbot_rules_passed": astrbot_passed,
                "issues": all_issues,
                "total_issues": len(all_issues),
                "reason": self._generate_reason(all_passed, satisfaction_score, all_issues)
            }
            
            return result
            
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_file)
            except Exception:
                pass
    
    def _generate_reason(self, passed: bool, score: int, issues: List[str]) -> str:
        """生成审查理由
        
        Args:
            passed: 是否通过
            score: 满意度分数
            issues: 问题列表
            
        Returns:
            str: 审查理由
        """
        if passed:
            if score >= 90:
                return f"代码质量优秀（满意度: {score}/100），所有检查均通过"
            elif score >= 80:
                return f"代码质量良好（满意度: {score}/100），有少量警告但不影响使用"
            else:
                return f"代码基本合格（满意度: {score}/100），建议优化"
        else:
            issue_count = len(issues)
            return f"代码存在 {issue_count} 个问题需要修复（满意度: {score}/100）"
    
    def audit_plugin_files(self, plugin_dir: str) -> Dict[str, Any]:
        """审查插件目录下的所有Python文件
        
        Args:
            plugin_dir: 插件目录路径
            
        Returns:
            Dict[str, Any]: 审查结果汇总
        """
        results = {}
        all_passed = True
        total_issues = []
        
        # 遍历插件目录
        for root, _, files in os.walk(plugin_dir):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            code = f.read()
                        
                        result = self.audit_code(code, file)
                        results[file] = result
                        
                        if not result['approved']:
                            all_passed = False
                        
                        total_issues.extend([f"{file}: {issue}" for issue in result['issues']])
                        
                    except Exception as e:
                        logger.error(f"审查文件 {file_path} 时出错: {str(e)}")
                        results[file] = {
                            "approved": False,
                            "error": str(e)
                        }
                        all_passed = False
        
        return {
            "approved": all_passed,
            "files": results,
            "total_issues": len(total_issues),
            "issues": total_issues
        }

# Trade Commission Cog - Modular Structure

## Overview
The tradecommission.py file (originally 1,897 lines) has been successfully split into 8 modular files for better maintainability.

## File Structure

### 1. **ui_components.py** (266 lines)
Standalone module containing UI-related classes and helpers:
- `extract_final_emoji()` - Helper function to extract emojis from text
- `AddInfoView` class - Discord UI View for the addinfo dropdown interface

### 2. **utils.py** (206 lines)
**UtilsMixin** class containing utility methods:
- `_has_addinfo_permission()` - Check user permissions
- `_delete_notification_after_delay()` - Delayed message deletion
- `_create_addinfo_embed()` - Create embed for addinfo panel
- `update_commission_message()` - Update the main trade commission message

### 3. **scheduling.py** (207 lines)
**SchedulingMixin** class for background task scheduling:
- `_check_schedule_loop()` - Main background loop
- `_check_guild_schedule()` - Per-guild schedule checking
- `_send_weekly_message()` - Send weekly trade commission message
- `_send_scheduled_notification()` - Send Sunday/Wednesday notifications

### 4. **commands_config.py** (373 lines)
**CommandsConfigMixin** class for basic configuration commands:
- `tc_schedule` - Schedule weekly messages
- `tc_disable` / `tc_enable` - Enable/disable functionality
- `tc_addrole` / `tc_removerole` / `tc_listroles` - Role management
- `tc_adduser` / `tc_removeuser` / `tc_listusers` - User management
- `tc_settitle` / `tc_setinitial` / `tc_setpost` - Message customization
- `tc_setpingrole` / `tc_setnotification` - Notification settings

### 5. **commands_options.py** (392 lines)
**CommandsOptionsMixin** class for option management:
- `tc_setoption` - Add/update trade options (global)
- `tc_removeoption` - Remove trade options (global)
- `tc_listoptions` - List all options (global)
- `tc_setimage` - Set commission image (global)
- `tc_setgrouptitle` / `tc_removegrouptitle` / `tc_listgrouptitles` - Emoji group titles

### 6. **commands_schedule.py** (195 lines)
**CommandsScheduleMixin** class for scheduling subcommands:
- `tc_sunday` group:
  - `sunday_enable` / `sunday_disable`
  - `sunday_time` / `sunday_message` / `sunday_pingrole`
  - `sunday_test`
- `tc_wednesday` group:
  - `wednesday_enable` / `wednesday_disable`
  - `wednesday_time` / `wednesday_message` / `wednesday_pingrole`
  - `wednesday_test`

### 7. **commands_actions.py** (246 lines)
**CommandsActionsMixin** class for action commands:
- `tc_post` - Manually post a message
- `tc_addinfo` - Open addinfo panel
- `tc_info` - Show configuration
- `tc_testnow` - Test weekly message (owner only)

### 8. **tradecommission.py** (350 lines)
Main cog file that:
- Inherits from all mixins
- Defines the `TradeCommission` class
- Contains `__init__`, `cog_load`, and `cog_unload` methods
- Defines the main `@commands.group` for tradecommission
- Contains wrapper methods that delegate to mixin implementations

## Benefits of This Structure

1. **Maintainability**: Each file has a clear, focused purpose
2. **Readability**: Easier to find and modify specific functionality
3. **Reusability**: Mixins can be tested independently
4. **Scalability**: Easy to add new features in appropriate modules
5. **Collaboration**: Multiple developers can work on different mixins simultaneously

## Architecture Pattern

The cog uses a **Mixin Pattern** where:
- Each mixin provides a specific set of related methods
- Mixins contain the implementation logic
- The main class inherits from all mixins and provides command wrappers
- Command decorators in the main file properly attach methods to the command group

## Import Structure

```python
# Main class imports all mixins
from .utils import UtilsMixin
from .scheduling import SchedulingMixin
from .commands_config import CommandsConfigMixin
from .commands_options import CommandsOptionsMixin
from .commands_schedule import CommandsScheduleMixin
from .commands_actions import CommandsActionsMixin

# Multiple inheritance
class TradeCommission(
    UtilsMixin,
    SchedulingMixin,
    CommandsConfigMixin,
    CommandsOptionsMixin,
    CommandsScheduleMixin,
    CommandsActionsMixin,
    commands.Cog
):
    ...
```

## Total Lines of Code
- **Original**: 1,897 lines (single file)
- **Refactored**: 2,245 lines (8 files)
- The increase is due to modular structure, imports, and wrapper methods

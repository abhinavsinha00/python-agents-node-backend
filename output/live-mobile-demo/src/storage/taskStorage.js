import AsyncStorage from '@react-native-async-storage/async-storage';

const TASKS_KEY = '@live_mobile_demo_tasks';
const SETTINGS_KEY = '@live_mobile_demo_settings';

export const loadTasks = async () => {
  try {
    const data = await AsyncStorage.getItem(TASKS_KEY);
    return data ? JSON.parse(data) : [];
  } catch (error) {
    console.error('Failed to load tasks', error);
    return [];
  }
};

export const saveTasks = async (tasks) => {
  try {
    await AsyncStorage.setItem(TASKS_KEY, JSON.stringify(tasks));
  } catch (error) {
    console.error('Failed to save tasks', error);
  }
};

export const loadSettings = async () => {
  try {
    const data = await AsyncStorage.getItem(SETTINGS_KEY);
    return data ? JSON.parse(data) : { theme: 'light', soundEnabled: true };
  } catch (error) {
    console.error('Failed to load settings', error);
    return { theme: 'light', soundEnabled: true };
  }
};

export const saveSettings = async (settings) => {
  try {
    await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch (error) {
    console.error('Failed to save settings', error);
  }
};

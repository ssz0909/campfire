export type AspectRatio = '9:16' | '16:9' | '1:1'
export const aspectRatioOptions = [
  { label: '竖屏 9:16', value: '9:16' },
  { label: '横屏 16:9', value: '16:9' },
  { label: '方形 1:1', value: '1:1' },
]
export type MusicMode = 'fixed' | 'random' | 'none' | 'model'
export const musicModeOptions = [
  { label: '从素材库随机选取', value: 'random' },
  { label: '固定一首音乐', value: 'fixed' },
  { label: '不使用配乐（静音）', value: 'none' },
  { label: '保留模型原声，不替换配乐', value: 'model' },
]
export const taskMusicModeOptions = [
  { label: '跟随工作区设置', value: 'workspace' },
  ...musicModeOptions,
]

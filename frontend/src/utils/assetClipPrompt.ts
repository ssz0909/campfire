import type { Asset } from '@/types/asset'

/** Build editable defaults locally, without a model call or generation charge. */
export function defaultClipPrompt(source: Asset): string {
  const vision = source.metadata?.vision_analysis
  const description = ((vision?.status === 'completed' || !vision?.status)
    ? vision?.visual_description?.trim() || vision?.caption?.trim() : '')
    || source.source_description?.trim()
  const facts = description
    ? '参考图片信息：' + description.slice(0, 900) + '。最终以图片实际可见内容为准。'
    : '以参考图片实际可见的主体、姿态和场景为准，不推测图片中不存在的内容。'
  const people = vision?.people_visible
  const motion = people === true
    ? '画面中的真人是动作主体：从前0.3秒开始，自然转头并带动上身轻转，在前3秒内呈现清晰的起始、动作变化与结束姿态；根据原图姿态调整为一个自然可行的动作。固定机位或轻微跟随，不能只有镜头拉远、眨眼或衣物晃动。'
    : people === false
      ? '围绕图片已有主体，用一次平稳的短距离侧移形成前后景层次；如图中确有水面、树叶等可动元素，可呈现自然细微动态，否则保持原有场景，不凭空添加动态元素或人物。'
      : '如图片中有真人，从前0.3秒开始安排一次符合可见姿态的自然转头或上身姿态变化，在前3秒内清楚完成，镜头固定或轻微跟随，不能只缩放照片；如无真人，用一次平稳的短距离侧移展示原有主体与空间，不新增人物。'
  return ['基于这张参考图片生成一个5秒连续动态分镜。' + facts, motion,
    '保持主体身份、服装、建筑与环境结构一致，构图突出原图主体，动作自然有吸引力；不驱动海报或雕塑中的人物，不新增人物、道具或设施，不做照片轮播，不生成字幕、水印或配乐。'].join('\n')
}

export function initialClipPrompt(source: Asset, clip?: Asset): string {
  const previous = clip?.metadata?.clip_library?.prompt
  return (typeof previous === 'string' && previous.trim() ? previous : defaultClipPrompt(source)).slice(0, 2000)
}

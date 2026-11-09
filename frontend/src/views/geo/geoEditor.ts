/** The server repeats normalization; arrays remain the source of truth for new drafts. */
export function geoPayload(form:any){
  const d=JSON.parse(JSON.stringify(form))
  d.service_items=d.service_items.filter((i:any)=>i.name.trim()||i.description.trim())
  d.faq_items=d.faq_items.filter((i:any)=>i.question.trim()||i.answer.trim())
  if(d.service_items.some((i:any)=>!i.name.trim()||!i.description.trim()))throw new Error('请为每条服务填写名称和说明，或删除未完成的条目')
  if(d.faq_items.some((i:any)=>!i.question.trim()||!i.answer.trim()))throw new Error('请为每条问答填写问题和回答，或删除未完成的条目')
  d.services=d.service_items.map((i:any)=>i.name+'：'+i.description).join('\n\n')
  d.faq=d.faq_items.map((i:any)=>'问：'+i.question+'\n答：'+i.answer).join('\n\n')
  if(d.service_items.length===1&&d.service_items[0].name==='产品与服务')d.services=d.service_items[0].description
  if(d.faq_items.length===1&&d.faq_items[0].question==='常见问题与回答')d.faq=d.faq_items[0].answer
  if(d.services.length>6000||d.faq.length>6000)throw new Error('服务或问答模块总计不能超过6000字，请精简内容')
  return d
}

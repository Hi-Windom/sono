import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'
import VConsole from 'vconsole'

const vc = new VConsole({
  theme: 'dark',
  disableLogScrolling: false,
})
// 隐藏默认的vConsole切换按钮，通过点击BuildInfo控件呼出
const vcBtn = document.getElementById('__vconsole')
if (vcBtn) {
  vcBtn.style.display = 'none'
}
// 将vConsole实例挂载到window，方便BuildInfo组件调用
;(window as any).__vconsole__ = vc

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

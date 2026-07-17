import {
  CatalogFactory,
  SurfaceControllerFactory,
  SurfaceController,
  SurfaceErrorCode,
  SurfaceEventType,
  UIRendererComponent
} from '@arkui-genius/genui_form'
import { common } from '@kit.AbilityKit'
import { util } from '@kit.ArkTS'

const RAWFILE_PATH: string = 'test.json'
const START_DELAY_MS: number = 300
const CONTROLLER_RESET_DELAY_MS: number = 120
const MESSAGE_FEED_DELAY_MS: number = 120
const RENDER_STABLE_DELAY_MS: number = 1000
const FORM_EXTENDED_CATALOG_ID: string = 'ohos.a2ui.extended.catalog.form'

interface RenderPayload {
  messages: string[]
}

@Entry
@Component
struct Index {
  @State controller: SurfaceController | null = null
  @State statusText: string = 'Starting render'

  private stopped: boolean = false

  aboutToAppear(): void {
    this.startRender()
  }

  aboutToDisappear(): void {
    this.stopped = true
    this.destroyController()
  }

  private async startRender(): Promise<void> {
    try {
      await this.sleep(START_DELAY_MS)
      if (this.stopped) {
        return
      }

      const context = this.getUIContext().getHostContext() as common.UIAbilityContext
      const payload = this.loadRenderPayload(context, RAWFILE_PATH)
      if (payload.messages.length === 0) {
        this.statusText = 'No DSL messages parsed'
        console.error(`No DSL messages parsed from rawfile/${RAWFILE_PATH}`)
        return
      }

      this.destroyController()
      await this.sleep(CONTROLLER_RESET_DELAY_MS)
      this.controller = this.createController()
      await this.sleep(CONTROLLER_RESET_DELAY_MS)

      for (let index = 0; index < payload.messages.length; index++) {
        if (this.stopped) {
          return
        }
        this.controller?.handleMessage(this.normalizeCatalogId(payload.messages[index]))
        await this.sleep(MESSAGE_FEED_DELAY_MS)
      }

      await this.sleep(RENDER_STABLE_DELAY_MS)
      this.statusText = `Rendered ${payload.messages.length} DSL messages`
      console.info(this.statusText)
    } catch (error) {
      this.statusText = `Render failed: ${error}`
      console.error(this.statusText)
    }
  }

  private createController(): SurfaceController {
    const controller = SurfaceControllerFactory.createSurfaceController({
      catalog: CatalogFactory.extended(),
      eventCallback: (eventType: SurfaceEventType, _ctrl: SurfaceController, surfaceId: string) => {
        console.info(`A2UI surface event: type=${eventType}, surfaceId=${surfaceId}`)
      }
    })
    controller.enableSchemaWarningReport(true)
    controller.registerErrorCallback((code: SurfaceErrorCode, errorMsg: string) => {
      console.error(`A2UI render error: code=${code}, message=${errorMsg}`)
    })
    return controller
  }

  private destroyController(): void {
    this.controller?.destroy()
    this.controller = null
  }

  private loadRenderPayload(context: common.UIAbilityContext, rawfilePath: string): RenderPayload {
    const fileData = context.resourceManager.getRawFileContentSync(rawfilePath)
    const decoderOptions: util.TextDecoderOptions = {
      fatal: false,
      ignoreBOM: true
    }
    const decodeOptions: util.DecodeToStringOptions = {
      stream: false
    }
    const textDecoder = util.TextDecoder.create('utf-8', decoderOptions)
    const jsonText = textDecoder.decodeToString(fileData, decodeOptions)
    const trimmedText = jsonText.trim()
    if (trimmedText.length === 0) {
      return { messages: [] }
    }

    if (trimmedText.startsWith('[')) {
      let parsed: Object[] | string[] = []
      try {
        parsed = JSON.parse(trimmedText) as Object[] | string[]
      } catch (error) {
        throw new Error(`Invalid JSON array in ${rawfilePath}: ${error}`)
      }

      if (!Array.isArray(parsed)) {
        return { messages: [] }
      }

      return {
        messages: parsed.map((message: Object | string): string => {
          if (typeof message === 'string') {
            return message
          }
          return JSON.stringify(message)
        })
      }
    }

    const messages: string[] = []
    const lines = trimmedText.split(/\r?\n/)
    for (let index = 0; index < lines.length; index++) {
      const line = lines[index].trim()
      if (line.length === 0) {
        continue
      }
      try {
        JSON.parse(line) as Object
      } catch (error) {
        throw new Error(`Invalid JSONL line ${index + 1} in ${rawfilePath}: ${error}`)
      }
      messages.push(line)
    }
    return { messages: messages }
  }

  private sleep(delayMs: number): Promise<void> {
    return new Promise<void>((resolve: () => void) => {
      setTimeout(resolve, delayMs)
    })
  }

  private normalizeCatalogId(message: string): string {
    return message.replace(
      /"catalogId"\s*:\s*"ohos\.a2ui\.extended\.catalog"/g,
      `"catalogId":"${FORM_EXTENDED_CATALOG_ID}"`
    )
  }

  @Builder
  _genuiFormDecl() {
    if (false) {
      Text('')
      Image('')
      Divider()
      Progress({ value: 0, total: 100 })
      Button('')
      Checkbox()
      Row() {}
      Column() {}
      Stack() {}
      Blank()
      List() {}
      ListItem() {}
      ForEach([], (item: string) => {
        Text(item)
      }, (item: string) => item)
    }
  }

  build() {
    Column() {
      if (this.controller !== null) {
        UIRendererComponent({
          surfaceController: this.controller
        })
      }
    }
    .width('100%')
    .height('100%')
    .alignItems(HorizontalAlign.Center)
    .justifyContent(FlexAlign.Start)
    .backgroundColor('#FFFFFF')
  }
}

import {
  CatalogFactory,
  SurfaceControllerFactory,
  SurfaceController,
  UIRendererComponent
} from '@arkui-genius/genui_form'
import { common } from '@kit.AbilityKit';
import { util } from '@kit.ArkTS';

@Entry
@Component
struct Index {
  @State controller: SurfaceController | undefined = undefined;

  aboutToAppear(): void {
    this.controller = SurfaceControllerFactory.createSurfaceController({
      catalog: CatalogFactory.extended()
    })

    const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
    const resourceMgr = context.resourceManager;
    const fileData: Uint8Array = resourceMgr.getRawFileContentSync('test.json');

    const textDecoderOptions: util.TextDecoderOptions = {
      fatal: false,
      ignoreBOM: true
    };
    const decodeToStringOptions: util.DecodeToStringOptions = {
      stream: false
    };
    const textDecoder = util.TextDecoder.create('utf-8', textDecoderOptions);
    const strContent = textDecoder.decodeToString(fileData, decodeToStringOptions);

    let a: object[] = JSON.parse(strContent);

    setTimeout(() => {
      a.forEach((obj: object) => {
        this.controller?.handleMessage(JSON.stringify(obj))
      })
    }, 3000)
  }

  build() {
    Column() {
      UIRendererComponent({
        surfaceController: this.controller
      })
    }
  }
}
